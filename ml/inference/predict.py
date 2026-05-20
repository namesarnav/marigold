"""Serving interface: rank concepts by forgetting risk.

This is the boundary the backend calls. It owns three decisions so no caller
has to make them:

1. Cold start vs. SAKT, via `should_use_sakt` / `blend` in ml.models.coldstart.
2. Loading the right artifacts, once, and reusing them.
3. Applying time decay, since SAKT itself has no notion of elapsed time.

## The `as_of` parameter, and what it does and does not do today

`as_of` is a real input, not a placeholder. It is used to compute elapsed time
since each concept was last practised, which drives the forgetting decay in
`apply_forgetting`.

It is deliberately not clamped to "now", so a caller may pass a *future*
datetime and get a projected P(correct) at that date. That is the hook the
exam-readiness feature will use — "how much will I remember on the 14th?" —
without changing this signature. What is not built is the feature around it:
scheduling simulation, revision planning, or any UI. The projection is a
straight decay forward from the last observed interaction; it does not model
reviews the user might do between now and the target date.

## Honest limits

Vanilla SAKT is order-based. It knows *what order* a user answered things in,
not *how long ago*. Marigold's premise is time-dependent forgetting, so a decay
is applied on top of the model output rather than learned inside it. That decay
is a documented heuristic (see `ml.config.ForgettingConfig`) with a fixed
half-life, not a fitted per-concept curve. The principled version is a
time-aware architecture — AKT's monotonic attention or a Hawkes-process KT —
which is a later slice. Keeping the heuristic separate and separately tested is
what makes that swap tractable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import torch

from ml.config import (
    ARTIFACTS_DIR,
    COLD_START,
    FORGETTING,
    SAKT,
    ColdStartConfig,
    ForgettingConfig,
    SAKTConfig,
)
from ml.data.sequences import PAD_ID, encode_interaction
from ml.models.coldstart import ConceptPrior, blend, should_use_sakt
from ml.models.sakt import SAKTModel


class HistoryUnavailable(RuntimeError):
    """Raised when a user's interaction history can be neither passed nor loaded."""


@dataclass(frozen=True)
class Interaction:
    """One past attempt, as the serving layer sees it.

    Mirrors a row from `GET /api/interactions/me`. `correct` is Optional
    because a skip carries no evidence about recall — see `backend/concepts.py`.
    Skips are dropped by `_usable`, never coerced to False.
    """

    concept_id: str
    correct: Optional[bool]
    responded_at: datetime
    response_time_ms: Optional[int] = None


@dataclass(frozen=True)
class ConceptScore:
    """A ranked concept, with enough provenance to explain the ranking."""

    concept_id: str
    p_correct: float
    source: str  # "prior" | "blend" | "sakt"
    days_since_last_review: Optional[float]
    n_interactions_on_concept: int


def _usable(interactions: Sequence[Interaction]) -> List[Interaction]:
    """Drop skips, then order oldest-first.

    Sorting here rather than trusting the caller means a ranking cannot silently
    depend on the order rows came back from the database.
    """
    graded = [i for i in interactions if i.correct is not None]
    return sorted(graded, key=lambda i: i.responded_at)


def apply_forgetting(
    p_correct: float,
    days_elapsed: Optional[float],
    config: ForgettingConfig = FORGETTING,
) -> float:
    """Decay a recall probability toward the floor as time passes.

    Exponential decay on the amount *above* the floor:

        p(t) = floor + (p0 - floor) * 2 ** (-t / half_life)

    Decaying toward a floor rather than toward zero matters: a four-option quiz
    can be guessed, so P(correct) has a hard lower bound no amount of forgetting
    goes below. Decaying toward 0 would rank never-seen material as more
    urgent than material the user has genuinely lost, which is backwards.

    `days_elapsed is None` means the concept has never been practised. No decay
    is applied — there is no "last review" to decay from, and the prior already
    represents an unpractised concept.
    """
    if days_elapsed is None or days_elapsed <= 0:
        return float(p_correct)

    decayed = config.floor + (p_correct - config.floor) * math.pow(
        2.0, -days_elapsed / config.half_life_days
    )
    # Guard the case where p_correct already sits below the floor.
    return float(min(max(decayed, 0.0), 1.0))


class ForgettingRanker:
    """Holds the loaded model and prior; ranks concepts for a user.

    Constructed once per process. The backend calls `rank` per request.
    """

    def __init__(
        self,
        model: Optional[SAKTModel] = None,
        prior: Optional[ConceptPrior] = None,
        concept_to_skill: Optional[Mapping[str, int]] = None,
        sakt_config: SAKTConfig = SAKT,
        cold_start_config: ColdStartConfig = COLD_START,
        forgetting_config: ForgettingConfig = FORGETTING,
        history_provider: Optional[Callable[[str], Sequence[Interaction]]] = None,
    ):
        # Supplies a user's past interactions when the caller does not pass them
        # explicitly. Injected rather than imported so this module stays free of
        # database and HTTP dependencies; the backend wires in a real loader at
        # startup. See `rank_concepts_by_forgetting_risk`.
        self.history_provider = history_provider
        self.model = model
        self.prior = prior or ConceptPrior(global_rate=0.5)
        # Maps Marigold concept ids to the model's contiguous skill indices.
        # Until a model is trained on Marigold's own concepts this is empty and
        # every concept takes the prior path, which is the correct behaviour
        # rather than a failure.
        self.concept_to_skill = dict(concept_to_skill or {})
        self.sakt_config = sakt_config
        self.cold_start_config = cold_start_config
        self.forgetting_config = forgetting_config

    # -- loading ----------------------------------------------------------

    @classmethod
    def from_artifacts(
        cls,
        checkpoint_path: Optional[Path] = None,
        prior_path: Optional[Path] = None,
        concept_map_path: Optional[Path] = None,
        device: str = "cpu",
        **kwargs,
    ) -> "ForgettingRanker":
        """Load from disk, tolerating missing artifacts.

        A missing checkpoint is not an error: it means every user is served by
        the prior. That is exactly the state Marigold is in before the first
        model is trained on real data, and the service must start and serve in
        it rather than crash-looping.
        """
        model = None
        if checkpoint_path is None:
            checkpoint_path = ARTIFACTS_DIR / "sakt_assistments09.pt"
        if Path(checkpoint_path).exists():
            payload = torch.load(checkpoint_path, map_location=device, weights_only=False)
            config = SAKTConfig(**payload["config"]) if "config" in payload else SAKT
            model = SAKTModel(payload["n_skills"], config)
            model.load_state_dict(payload["state_dict"])
            model.to(device)
            model.eval()

        prior = None
        if prior_path is not None and Path(prior_path).exists():
            prior = ConceptPrior.load(Path(prior_path))

        concept_map = None
        if concept_map_path is not None and Path(concept_map_path).exists():
            import json

            concept_map = json.loads(Path(concept_map_path).read_text())

        return cls(model=model, prior=prior, concept_to_skill=concept_map, **kwargs)

    # -- prediction -------------------------------------------------------

    def _sakt_predictions(
        self, history: Sequence[Interaction], candidates: Sequence[str]
    ) -> Dict[str, float]:
        """Batch a SAKT forward pass for every candidate concept.

        Returns {} when SAKT cannot be applied: no model, or none of the
        candidate concepts map to a skill the model was trained on. Returning
        empty rather than raising lets the caller fall through to the prior.
        """
        if self.model is None or not self.concept_to_skill:
            return {}

        mapped = [c for c in candidates if c in self.concept_to_skill]
        if not mapped:
            return {}

        # Build the shared history context once: the same past sequence is used
        # for every candidate, only the final query differs.
        hist_skills = []
        hist_correct = []
        for item in history:
            skill = self.concept_to_skill.get(item.concept_id)
            if skill is None:
                # A concept the model never saw contributes nothing meaningful
                # to attention; dropping it is better than mapping it to an
                # arbitrary index.
                continue
            hist_skills.append(skill)
            hist_correct.append(int(bool(item.correct)))

        if not hist_skills:
            return {}

        max_len = self.sakt_config.max_seq_len
        # Keep the most recent context, leaving one slot for the query step.
        hist_skills = hist_skills[-(max_len - 1) :]
        hist_correct = hist_correct[-(max_len - 1) :]

        n_skills = self.model.n_skills
        interactions = encode_interaction(
            np.array(hist_skills, dtype=np.int64),
            np.array(hist_correct, dtype=np.int64),
            n_skills,
        )

        length = len(interactions)
        device = next(self.model.parameters()).device

        past = np.full((len(mapped), max_len), PAD_ID, dtype=np.int64)
        query = np.full((len(mapped), max_len), PAD_ID, dtype=np.int64)

        for row, concept_id in enumerate(mapped):
            past[row, :length] = interactions
            # Queries at context positions are filled with the skill actually
            # answered at that step; only the final position is the question we
            # care about, read back below.
            query[row, : length - 1] = np.array(hist_skills[1:], dtype=np.int64) + 1
            query[row, length - 1] = self.concept_to_skill[concept_id] + 1

        with torch.no_grad():
            logits = self.model(
                torch.from_numpy(past).to(device), torch.from_numpy(query).to(device)
            )
            probs = torch.sigmoid(logits).cpu().numpy()

        # The prediction for the candidate is at the last real position.
        return {
            concept_id: float(probs[row, length - 1])
            for row, concept_id in enumerate(mapped)
        }

    def rank(
        self,
        user_id: str,
        candidate_concepts: Sequence[str],
        as_of: datetime,
        history: Sequence[Interaction],
    ) -> List[ConceptScore]:
        """Rank candidates by ascending P(correct) — highest risk first."""
        usable = _usable(history)
        n_total = len(usable)

        # Per-concept aggregates, used by both the prior path and the decay.
        last_seen: Dict[str, datetime] = {}
        attempts: Dict[str, int] = {}
        successes: Dict[str, int] = {}
        for item in usable:
            attempts[item.concept_id] = attempts.get(item.concept_id, 0) + 1
            successes[item.concept_id] = successes.get(item.concept_id, 0) + int(
                bool(item.correct)
            )
            prev = last_seen.get(item.concept_id)
            if prev is None or item.responded_at > prev:
                last_seen[item.concept_id] = item.responded_at

        sakt_probs = (
            self._sakt_predictions(usable, candidate_concepts)
            if should_use_sakt(n_total, self.cold_start_config)
            else {}
        )

        scores: List[ConceptScore] = []
        for concept_id in candidate_concepts:
            prior_p = self.prior.predict_for_user(
                concept_id,
                user_correct=successes.get(concept_id, 0),
                user_attempts=attempts.get(concept_id, 0),
            )
            combined, source = blend(
                prior_probability=prior_p,
                sakt_probability=sakt_probs.get(concept_id),
                user_interaction_count=n_total,
                config=self.cold_start_config,
            )

            seen_at = last_seen.get(concept_id)
            days = None
            if seen_at is not None:
                days = (as_of - seen_at).total_seconds() / 86400.0

            scores.append(
                ConceptScore(
                    concept_id=concept_id,
                    p_correct=apply_forgetting(combined, days, self.forgetting_config),
                    source=source,
                    days_since_last_review=days,
                    n_interactions_on_concept=attempts.get(concept_id, 0),
                )
            )

        # Ascending P(correct): most likely to be forgotten first. Ties break on
        # concept_id so the ordering is total and reproducible rather than
        # dependent on sort stability over an arbitrary input order.
        scores.sort(key=lambda s: (s.p_correct, s.concept_id))
        return scores


# Module-level singleton, built lazily so importing this module is cheap and
# does not touch the filesystem.
_DEFAULT_RANKER: Optional[ForgettingRanker] = None


def get_ranker() -> ForgettingRanker:
    global _DEFAULT_RANKER
    if _DEFAULT_RANKER is None:
        _DEFAULT_RANKER = ForgettingRanker.from_artifacts()
    return _DEFAULT_RANKER


def set_ranker(ranker: Optional[ForgettingRanker]) -> None:
    """Override the singleton. For tests and for warm-loading at startup."""
    global _DEFAULT_RANKER
    _DEFAULT_RANKER = ranker


def rank_concepts_by_forgetting_risk(
    user_id: str,
    candidate_concepts: List[str],
    as_of: datetime,
    history: Optional[Sequence[Interaction]] = None,
) -> List[Tuple[str, float]]:
    """Returns candidate_concepts sorted by ascending P(correct),
    i.e. highest forgetting risk first.

    `history` is the user's past interactions, as returned by
    `GET /api/interactions/me`. When omitted, it is fetched through the ranker's
    configured `history_provider`, which keeps this signature exactly as
    specified while keeping database access out of this module.

    Raises `HistoryUnavailable` if history is neither passed nor obtainable.
    That is deliberate: silently ranking on an empty history would return
    plausible-looking prior-only numbers for a user who actually has months of
    data, and nothing downstream would notice. Failing loudly is the only safe
    behaviour for a wrong answer that looks right.

    `as_of` may be in the future — see the module docstring on exam readiness.
    """
    ranker = get_ranker()

    if history is None:
        if ranker.history_provider is None:
            raise HistoryUnavailable(
                "No history was passed and no history_provider is configured. "
                "Either pass history=... explicitly, or call set_ranker() with a "
                "ForgettingRanker constructed with history_provider=<loader>."
            )
        history = ranker.history_provider(user_id)

    scored = ranker.rank(
        user_id=user_id,
        candidate_concepts=candidate_concepts,
        as_of=as_of,
        history=history,
    )
    return [(s.concept_id, s.p_correct) for s in scored]
