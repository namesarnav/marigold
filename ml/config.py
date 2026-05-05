"""Central configuration for the knowledge-tracing pipeline.

Every nontrivial modelling choice lives here with the reason it was chosen, so
the judgment calls are reviewable in one place rather than scattered through the
code as magic numbers.
"""

from dataclasses import dataclass
from pathlib import Path

ML_ROOT = Path(__file__).resolve().parent
DATA_DIR = ML_ROOT / "data" / "raw"
ARTIFACTS_DIR = ML_ROOT / "artifacts"


@dataclass(frozen=True)
class SAKTConfig:
    """SAKT architecture and optimisation settings.

    Judgment calls, with reasoning:

    max_seq_len = 200
        The attention matrix is O(L^2) in both time and memory, and the median
        ASSISTments student has well under 200 interactions, so 200 captures
        nearly all students' full history without paying for a longer window.
        Longer sequences are chunked rather than truncated so no interaction is
        silently discarded. Marigold sequences will be far shorter than this for
        a long time.

    d_model = 128
        The SAKT paper sweeps 50-200. 128 sits mid-range and keeps the model
        around 1M parameters, which matters because inference has to run on a
        CPU-only t4g instance sharing 2GB of RAM with Postgres and the API.

    n_heads = 8
        128 / 8 = 16 dimensions per head. The paper uses 5 heads at d=200 (40
        per head); 8 heads at 16 dims each trades head width for more distinct
        attention patterns, which suits the many-skill setting.

    dropout = 0.2
        The paper's value. Knowledge-tracing datasets overfit quickly because
        one student contributes many correlated interactions.

    lr = 1e-3 with Adam
        Standard for this model size. The training loop early-stops on
        validation AUC rather than relying on a fixed schedule.
    """

    max_seq_len: int = 200
    d_model: int = 128
    n_heads: int = 8
    dropout: float = 0.2
    ffn_hidden: int = 256

    lr: float = 1e-3
    batch_size: int = 64
    max_epochs: int = 30
    early_stopping_patience: int = 5
    weight_decay: float = 1e-5
    grad_clip: float = 5.0
    seed: int = 1337


@dataclass(frozen=True)
class SplitConfig:
    """Per-student temporal split settings.

    holdout_n = 10
        Each student's most recent 10 interactions form the eval set. Fixed-N
        rather than a fixed fraction so every student contributes the same
        amount of evaluation signal — a fraction would let the handful of
        students with 1000+ interactions dominate the AUC.

    max_holdout_fraction = 0.5
        Guards the fixed N: a student with 12 interactions must not have 10 of
        them held out, or their eval predictions would be made with almost no
        history and would measure cold-start behaviour rather than SAKT.

    min_train_interactions = 5
        Students with fewer than this remaining after the split are dropped.
        They are not useful for benchmarking a sequence model, and keeping them
        would depress AUC for reasons unrelated to the architecture.
    """

    holdout_n: int = 10
    max_holdout_fraction: float = 0.5
    min_train_interactions: int = 5


@dataclass(frozen=True)
class ColdStartConfig:
    """Cold-start fallback settings. See ml/models/coldstart.py.

    min_interactions_for_sakt = 20
        Below roughly 20 interactions a SAKT sequence is mostly padding and its
        attention has little to attend to, so its output is dominated by the
        learned bias rather than the student. 20 is a deliberate round number,
        not a tuned value — it should be re-derived against real Marigold data
        once there is enough of it (see `calibrate_threshold` note in the
        module docstring).

    blend_window = 20
        Interactions over which to ramp from prior to SAKT once the threshold
        is crossed. A hard switch would make a user's recommendations jump
        discontinuously on a single interaction, which is visible and
        confusing in a review feed.

    prior_strength = 20.0
        Pseudo-count for Beta smoothing of a concept's difficulty prior. A
        concept with 2 observations should sit near the global mean, not at
        0.0 or 1.0.
    """

    min_interactions_for_sakt: int = 20
    blend_window: int = 20
    prior_strength: float = 20.0


@dataclass(frozen=True)
class ForgettingConfig:
    """Time-decay applied on top of a knowledge-tracing prediction.

    Vanilla SAKT is order-based: it consumes a sequence of interactions and has
    no notion of wall-clock elapsed time. Marigold's whole premise is predicting
    *forgetting*, which is inherently time-dependent, so an explicit decay is
    applied on top of the model output.

    This is a heuristic, not a learned component, and it is deliberately kept
    separate and testable rather than hidden inside the model. The principled
    upgrade is a time-aware architecture (AKT's monotonic attention, or
    HawkesKT) that learns decay from data; that is a later slice.

    half_life_days = 7.0
        The retention half-life toward which a prediction decays. Seven days is
        a defensible default from the spacing-effect literature for
        recently-learned material, and is a starting point to be fit per
        concept once Marigold has repeat-review data.

    floor = 0.25
        Predictions decay toward this floor, not toward zero. Even fully
        forgotten material is sometimes recalled or guessed, and a
        four-option quiz has a 0.25 chance floor by construction.
    """

    half_life_days: float = 7.0
    floor: float = 0.25


SAKT = SAKTConfig()
SPLIT = SplitConfig()
COLD_START = ColdStartConfig()
FORGETTING = ForgettingConfig()
