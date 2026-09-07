"""The seam between the API and the knowledge-tracing library in `ml/`.

Everything that knows about both lives here, and nothing else in the backend
imports `ml`. That keeps the coupling in one reviewable file: `ml/` stays a
library with no database or HTTP dependency, and the routes stay free of model
concerns.

Three things this is responsible for.

**Translating the log.** `ml.inference.predict.Interaction` and the backend's
`Interaction` row already agree field for field — `concept_id`, `correct`,
`responded_at`, `response_time_ms` — with one difference: concept ids are
integers here and strings there. `_to_ml_interaction` is the whole conversion.

**Holding the ranker.** `ForgettingRanker.from_artifacts()` is a per-process
object, not a per-request one, so it is built once and cached. A missing
checkpoint is not an error: it means every user is served by the cold-start
prior, which is exactly Marigold's state until a model is trained on its own
data.

**Degrading rather than failing.** A ranking is a nice-to-have on top of a study
app. If the model cannot be loaded or the forward pass raises, the caller gets
concepts ordered by the fallback below instead of a 500 — a study queue in a
slightly worse order beats no study queue.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import List, Optional, Sequence

from sqlalchemy.orm import Session

from .concepts import interaction_sequence
from .models import Concept, Interaction

logger = logging.getLogger(__name__)

# How much history the ranking reads. SAKT attends over a bounded window
# (200 by default), and the prior only needs per-concept counts, so more than
# this buys nothing and costs a larger query on every request.
HISTORY_LIMIT = 1000


@lru_cache(maxsize=1)
def get_ranker():
    """The process-wide ranker, built on first use.

    Deliberately lazy rather than constructed at import: loading a checkpoint at
    module scope would run inside the Alembic migration step too, and a slow or
    failing load would then break a deploy rather than one endpoint.
    """
    from ml.inference.predict import ForgettingRanker

    ranker = ForgettingRanker.from_artifacts()
    logger.info(
        "Forgetting ranker ready (sakt_model=%s). %s",
        ranker.model is not None,
        "SAKT available for mapped concepts."
        if ranker.model is not None
        else "No checkpoint; every concept is served by the cold-start prior.",
    )
    return ranker


def _to_ml_interaction(row: Interaction):
    """One log row in the shape `ml/` expects.

    Skips (`correct is None`) are passed through untouched, not dropped here —
    `ml` filters them itself and is tested for it. Coercing a skip to False
    would teach the model that running out of time means forgetting.
    """
    from ml.inference.predict import Interaction as MLInteraction

    return MLInteraction(
        concept_id=str(row.concept_id),
        correct=row.correct,
        responded_at=_as_utc(row.responded_at),
        response_time_ms=row.response_time_ms,
    )


def _as_utc(value: datetime) -> datetime:
    """Attach UTC to a naive timestamp.

    Rows are stored naive; the ranking subtracts `responded_at` from `as_of` to
    get elapsed days, and mixing naive and aware datetimes raises. Treating
    stored values as UTC matches how they are written.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _fallback_order(concepts: Sequence[Concept], counts: dict) -> List[Concept]:
    """Least-practised first, used when the model is unavailable.

    Not a forgetting estimate and not presented as one — the response marks
    these `source="unavailable"` so a caller cannot mistake the two.
    """
    return sorted(concepts, key=lambda c: (counts.get(c.id, 0), c.label or ""))


def rank_user_concepts(
    db: Session,
    user_id: int,
    *,
    as_of: Optional[datetime] = None,
    limit: Optional[int] = None,
):
    """Rank a user's concepts by how likely they are to have forgotten them.

    Returns a list of `(Concept, ConceptScore | None)`, most at-risk first. The
    score is None only on the degraded path, where the order comes from
    `_fallback_order` instead.

    `as_of` defaults to now and may be in the future: the underlying model
    projects forward, which is the exam-readiness hook. It does not model
    reviews the user might do between now and then.
    """
    as_of = as_of or datetime.now(timezone.utc)

    concepts = (
        db.query(Concept)
        .filter(Concept.user_id == user_id)
        .order_by(Concept.id.asc())
        .all()
    )
    if not concepts:
        return []

    history_rows = interaction_sequence(db, user_id, limit=HISTORY_LIMIT)

    by_id = {str(c.id): c for c in concepts}
    counts: dict = {}
    for row in history_rows:
        if row.concept_id is not None:
            counts[row.concept_id] = counts.get(row.concept_id, 0) + 1

    try:
        ranker = get_ranker()
        scores = ranker.rank(
            str(user_id),
            list(by_id.keys()),
            as_of,
            # Passed explicitly rather than through a `history_provider`, so
            # this module never has to hand `ml` a database session and the
            # library's HistoryUnavailable path cannot be reached.
            history=[_to_ml_interaction(r) for r in history_rows],
        )
    except Exception:  # noqa: BLE001 - any model failure degrades, never 500s
        logger.exception(
            "Forgetting ranking failed for user %s; falling back to least-practised order.",
            user_id,
        )
        degraded = [(c, None) for c in _fallback_order(concepts, counts)]
        return degraded[:limit] if limit else degraded

    ranked = [(by_id[s.concept_id], s) for s in scores if s.concept_id in by_id]
    return ranked[:limit] if limit else ranked
