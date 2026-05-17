"""Cold-start fallback for users with too little history for SAKT.

## Which fallback, and why

The brief offered BKT or a population-average per-concept difficulty prior.
**This implements the population-average prior**, for two reasons:

1. *Correctness per unit of complexity.* BKT needs four parameters per concept
   (prior knowledge, learn rate, slip, guess) fit by EM or a grid search.
   EM on BKT is genuinely fiddly — it is sensitive to initialisation and
   routinely converges to degenerate parameters (slip + guess > 1, the
   "model degeneracy" problem in the BKT literature) that produce predictions
   which get *worse* as a student answers more correctly. Detecting and
   constraining that is more machinery than the cold-start path deserves, and
   subtle wrongness in the fallback is worse than a simple estimator: the
   fallback is exactly what a brand-new user sees.

2. *It matches what cold start actually knows.* With fewer than ~20
   interactions there is not enough signal to identify a per-student learning
   trajectory, which is the only thing BKT gives that a prior does not. What is
   available is "how hard is this concept for people in general, nudged by the
   little we have seen from this user" — which is precisely a smoothed prior.

The estimator is a Beta-Bernoulli posterior mean: a concept's difficulty is its
observed success rate shrunk toward the global mean by a pseudo-count. That
gives sane behaviour at every sample size for free — a concept with two
observations sits near the global mean rather than at 0.0 or 1.0.

BKT remains the right upgrade if per-concept *learning rate* becomes something
the product needs to model, and the interface here would not have to change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from ml.config import COLD_START, ColdStartConfig


def should_use_sakt(
    user_interaction_count: int, config: ColdStartConfig = COLD_START
) -> bool:
    """Whether a user has enough history for SAKT to be trusted.

    Named and isolated on purpose: this decision determines which model a
    prediction came from, so it must be greppable, unit-testable, and
    impossible to drift out of sync with a second copy of the same comparison
    written inline somewhere else.
    """
    return user_interaction_count >= config.min_interactions_for_sakt


def sakt_blend_weight(
    user_interaction_count: int, config: ColdStartConfig = COLD_START
) -> float:
    """Weight on the SAKT prediction, in [0, 1]; the rest goes to the prior.

    A hard switch at the threshold would make a user's review queue reorder
    visibly on a single interaction. Instead the weight ramps linearly from 0 at
    the threshold to 1 after `blend_window` further interactions.

    Below the threshold this is 0, so `should_use_sakt` and this function never
    disagree about whether SAKT is contributing.
    """
    if not should_use_sakt(user_interaction_count, config):
        return 0.0
    if config.blend_window <= 0:
        return 1.0

    progress = (
        user_interaction_count - config.min_interactions_for_sakt
    ) / config.blend_window
    return float(min(1.0, max(0.0, progress)))


@dataclass
class ConceptPrior:
    """Population difficulty prior, one smoothed success rate per concept."""

    global_rate: float
    concept_rates: Dict[str, float] = field(default_factory=dict)
    concept_counts: Dict[str, int] = field(default_factory=dict)
    prior_strength: float = COLD_START.prior_strength

    def predict(self, concept_id: str) -> float:
        """P(correct) for a concept, for a user we know nothing about."""
        return self.concept_rates.get(concept_id, self.global_rate)

    def predict_for_user(
        self,
        concept_id: str,
        user_correct: int = 0,
        user_attempts: int = 0,
    ) -> float:
        """P(correct), folding in whatever little the user has shown us.

        The concept prior acts as the Beta prior and the user's own attempts on
        that concept as the observations, so a user who has answered a concept
        twice is nudged away from the population rate without being defined by
        two data points.
        """
        base = self.predict(concept_id)
        if user_attempts <= 0:
            return base

        pseudo = self.prior_strength
        return float(
            (base * pseudo + user_correct) / (pseudo + user_attempts)
        )

    def to_dict(self) -> Dict:
        return {
            "global_rate": self.global_rate,
            "concept_rates": self.concept_rates,
            "concept_counts": self.concept_counts,
            "prior_strength": self.prior_strength,
        }

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_dict(cls, payload: Mapping) -> "ConceptPrior":
        return cls(
            global_rate=float(payload["global_rate"]),
            concept_rates=dict(payload.get("concept_rates", {})),
            concept_counts={
                k: int(v) for k, v in payload.get("concept_counts", {}).items()
            },
            prior_strength=float(payload.get("prior_strength", COLD_START.prior_strength)),
        )

    @classmethod
    def load(cls, path: Path) -> "ConceptPrior":
        return cls.from_dict(json.loads(Path(path).read_text()))


def fit_concept_prior(
    observations: Iterable[Tuple[str, bool]],
    config: ColdStartConfig = COLD_START,
) -> ConceptPrior:
    """Fit the prior from (concept_id, correct) pairs across all users.

    Skipped interactions must be filtered out by the caller — a skip carries no
    evidence about recall, and counting it as incorrect would make every
    concept look harder than it is. See `backend/concepts.py`, which records
    skips as `correct = NULL` precisely so they can be excluded here.
    """
    counts: Dict[str, int] = {}
    successes: Dict[str, int] = {}

    total = 0
    total_correct = 0

    for concept_id, correct in observations:
        counts[concept_id] = counts.get(concept_id, 0) + 1
        successes[concept_id] = successes.get(concept_id, 0) + int(bool(correct))
        total += 1
        total_correct += int(bool(correct))

    # With no data at all, 0.5 is the only honest answer: maximum uncertainty.
    global_rate = total_correct / total if total else 0.5

    pseudo = config.prior_strength
    concept_rates = {
        concept_id: (global_rate * pseudo + successes[concept_id])
        / (pseudo + counts[concept_id])
        for concept_id in counts
    }

    return ConceptPrior(
        global_rate=float(global_rate),
        concept_rates=concept_rates,
        concept_counts=counts,
        prior_strength=pseudo,
    )


def blend(
    prior_probability: float,
    sakt_probability: Optional[float],
    user_interaction_count: int,
    config: ColdStartConfig = COLD_START,
) -> Tuple[float, str]:
    """Combine the two predictions and say which path produced the result.

    Returns `(probability, source)` where source is one of "prior", "blend", or
    "sakt". Returning the source rather than logging it means callers can
    surface *why* a recommendation was made, and tests can assert on the branch
    taken instead of inferring it from a number.
    """
    if sakt_probability is None:
        return float(prior_probability), "prior"

    weight = sakt_blend_weight(user_interaction_count, config)
    if weight <= 0.0:
        return float(prior_probability), "prior"
    if weight >= 1.0:
        return float(sakt_probability), "sakt"

    blended = (1.0 - weight) * prior_probability + weight * sakt_probability
    return float(blended), "blend"
