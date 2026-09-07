"""What to study next.

The product feature the interaction log was always being collected for: rather
than showing decks in the order they were uploaded, rank the user's concepts by
how likely they are to have forgotten them.

The ranking itself lives in `ml/` and is reached through `backend.review`, which
is the only module in the backend that imports it.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_verified_user
from ..models import Flashcard, Interaction, User
from ..review import rank_user_concepts
from ..schemas import ReviewConceptOut, ReviewQueueOut

router = APIRouter(prefix="/api/review", tags=["review"])

# A study session, not a data dump. The queue is something a person works
# through, so the default is a sitting's worth and the cap keeps the response
# bounded for an account with a large library.
DEFAULT_LIMIT = 20
MAX_LIMIT = 200


@router.get("/next", response_model=ReviewQueueOut)
def review_queue(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    as_of: Optional[datetime] = Query(
        default=None,
        description=(
            "Score as if it were this moment. Defaults to now. A future date "
            "projects forward — 'what will I have forgotten by my exam' — but "
            "does not account for reviews done between now and then. "
            "Use a Z suffix (2027-01-01T00:00:00Z) or URL-encode the value: an "
            "unencoded '+00:00' offset decodes to a space and is rejected."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_verified_user),
):
    """Concepts ranked by forgetting risk, most at-risk first.

    A concept the user has never practised is included and scored by the
    population prior, so a new library is a usable queue rather than an empty
    one. Note the ordering consequence, which is a deliberate product choice:
    something studied once and long forgotten ranks *above* something never
    seen, because the estimate for the former has decayed below the prior. The
    `source` and `interaction_count` on each row are what a caller uses to
    present those differently.
    """
    if as_of is not None and as_of.tzinfo is None:
        # A naive query value is ambiguous, and the ranking compares it against
        # timestamps this app writes in UTC.
        as_of = as_of.replace(tzinfo=timezone.utc)

    ranked = rank_user_concepts(db, current_user.id, as_of=as_of, limit=limit)

    if not ranked:
        return ReviewQueueOut(
            as_of=(as_of or datetime.now(timezone.utc)).isoformat(),
            count=0,
            model_available=False,
            concepts=[],
        )

    concept_ids = [c.id for c, _ in ranked]

    card_counts = dict(
        db.query(Flashcard.concept_id, func.count(Flashcard.id))
        .filter(Flashcard.concept_id.in_(concept_ids))
        .group_by(Flashcard.concept_id)
        .all()
    )
    interaction_counts = dict(
        db.query(Interaction.concept_id, func.count(Interaction.id))
        .filter(
            Interaction.user_id == current_user.id,
            Interaction.concept_id.in_(concept_ids),
        )
        .group_by(Interaction.concept_id)
        .all()
    )

    rows: List[ReviewConceptOut] = []
    for concept, score in ranked:
        rows.append(
            ReviewConceptOut(
                concept_id=concept.id,
                key=concept.key,
                label=concept.label,
                card_count=card_counts.get(concept.id, 0),
                interaction_count=interaction_counts.get(concept.id, 0),
                p_correct=None if score is None else round(score.p_correct, 4),
                # "unavailable" is a distinct value rather than a null source:
                # the rows still come back in a usable order, and a caller that
                # treats that order as a forgetting estimate would be wrong.
                source="unavailable" if score is None else score.source,
                days_since_last_review=(
                    None if score is None else score.days_since_last_review
                ),
            )
        )

    return ReviewQueueOut(
        as_of=(as_of or datetime.now(timezone.utc)).isoformat(),
        count=len(rows),
        model_available=any(r.source in ("sakt", "blend") for r in rows),
        concepts=rows,
    )
