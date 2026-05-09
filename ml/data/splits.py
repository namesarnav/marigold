"""Per-student temporal splitting.

This is the single highest-risk function in the pipeline. A random split over
individual interactions inflates AUC dramatically, because a student's answer to
skill S at step 40 is highly predictive of their answer to skill S at step 41 —
if one is in train and the other in test, the model is scored on information it
was trained on. Published knowledge-tracing results that look "too good" are
very often this bug.

The rule enforced here: for each student, the most recent N interactions go to
eval, everything earlier goes to train, and no interaction is ever in both.

One design decision worth being explicit about, because it *looks* like leakage
and is not: an eval sequence is allowed to use the student's training-period
interactions as **context**. At serving time you genuinely do know a user's
past when predicting their next answer, so conditioning on it is realistic.
What would be leakage is conditioning on interactions at or after the position
being predicted. `build_eval_windows` scores only held-out positions and always
draws context from strictly earlier steps.
"""

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import numpy as np

from ml.config import SPLIT, SplitConfig


@dataclass(frozen=True)
class StudentSequence:
    """One student's ordered interaction history.

    `order` is the explicit ordering key. It is kept separate from list position
    so the caller decides what "temporal" means: wall-clock timestamps for
    Marigold, log order for benchmark data that has no usable clock.
    """

    student_id: int
    skills: np.ndarray  # int64, shape (T,)
    correct: np.ndarray  # int8, shape (T,)
    order: np.ndarray  # int64, shape (T,) — monotonically non-decreasing

    def __len__(self) -> int:
        return int(self.skills.shape[0])


@dataclass(frozen=True)
class TemporalSplit:
    """Result of splitting one student's history in two."""

    student_id: int
    train_skills: np.ndarray
    train_correct: np.ndarray
    eval_skills: np.ndarray
    eval_correct: np.ndarray
    # Index into the original history where the eval portion begins. Retained so
    # callers (and tests) can verify the boundary rather than trusting it.
    split_index: int


def holdout_size(
    n_interactions: int, config: SplitConfig = SPLIT
) -> int:
    """How many of a student's most recent interactions to hold out.

    Fixed N, capped so a short history is never mostly eval. Returns 0 when the
    student cannot support a split at all, which the caller treats as "drop".

    Deterministic and dependent only on the length, so the split is reproducible
    without a random seed.
    """
    if n_interactions <= 0:
        return 0

    n_holdout = min(config.holdout_n, int(n_interactions * config.max_holdout_fraction))
    if n_holdout < 1:
        return 0
    if n_interactions - n_holdout < config.min_train_interactions:
        return 0
    return n_holdout


def split_student_temporal(
    sequence: StudentSequence, config: SplitConfig = SPLIT
) -> TemporalSplit | None:
    """Split one student: earlier interactions train, most recent N eval.

    Returns None when the student is too short to split usefully.

    The input is sorted by `order` first. Sorting is stable, so interactions
    sharing an order value (common in exported logs where many events carry the
    same coarse timestamp) keep their original relative order rather than being
    silently permuted.
    """
    n = len(sequence)
    n_holdout = holdout_size(n, config)
    if n_holdout == 0:
        return None

    order_idx = np.argsort(sequence.order, kind="stable")
    skills = sequence.skills[order_idx]
    correct = sequence.correct[order_idx]

    split_index = n - n_holdout
    return TemporalSplit(
        student_id=sequence.student_id,
        train_skills=skills[:split_index],
        train_correct=correct[:split_index],
        eval_skills=skills[split_index:],
        eval_correct=correct[split_index:],
        split_index=split_index,
    )


def split_all_students(
    sequences: Sequence[StudentSequence], config: SplitConfig = SPLIT
) -> List[TemporalSplit]:
    """Split every student, dropping those too short to split.

    Order of the output follows the order of the input, so the whole operation
    is deterministic with no reliance on dict iteration or RNG.
    """
    splits = []
    for seq in sequences:
        split = split_student_temporal(seq, config)
        if split is not None:
            splits.append(split)
    return splits


def group_interactions_by_student(
    student_ids: np.ndarray,
    skills: np.ndarray,
    correct: np.ndarray,
    order: np.ndarray,
) -> List[StudentSequence]:
    """Turn a flat interaction table into per-student sequences.

    Students are emitted in ascending id order so downstream splits and batches
    are reproducible run to run.
    """
    sequences: List[StudentSequence] = []
    for student_id in np.unique(student_ids):
        mask = student_ids == student_id
        sequences.append(
            StudentSequence(
                student_id=int(student_id),
                skills=skills[mask].astype(np.int64),
                correct=correct[mask].astype(np.int8),
                order=order[mask].astype(np.int64),
            )
        )
    return sequences


def split_summary(splits: Sequence[TemporalSplit]) -> Dict[str, float]:
    """Aggregate counts, for logging and for asserting on in tests."""
    if not splits:
        return {
            "students": 0,
            "train_interactions": 0,
            "eval_interactions": 0,
            "mean_train_len": 0.0,
            "eval_positive_rate": 0.0,
        }

    train_total = sum(len(s.train_skills) for s in splits)
    eval_total = sum(len(s.eval_skills) for s in splits)
    eval_positives = sum(int(s.eval_correct.sum()) for s in splits)
    return {
        "students": len(splits),
        "train_interactions": train_total,
        "eval_interactions": eval_total,
        "mean_train_len": train_total / len(splits),
        "eval_positive_rate": eval_positives / eval_total if eval_total else 0.0,
    }


def assert_no_leakage(
    sequences: Sequence[StudentSequence], splits: Sequence[TemporalSplit]
) -> None:
    """Verify the split invariants directly, by reconstruction.

    Cheap enough to run on every training job, and it catches the failure mode
    that matters — a train/eval boundary that drifts — at the point it happens
    rather than via a suspiciously high AUC days later.
    """
    by_id = {seq.student_id: seq for seq in sequences}

    for split in splits:
        original = by_id[split.student_id]
        order_idx = np.argsort(original.order, kind="stable")
        skills = original.skills[order_idx]
        correct = original.correct[order_idx]

        # Train + eval must reconstruct the original history exactly: nothing
        # duplicated across the boundary, nothing dropped, order preserved.
        rebuilt_skills = np.concatenate([split.train_skills, split.eval_skills])
        rebuilt_correct = np.concatenate([split.train_correct, split.eval_correct])
        if not np.array_equal(rebuilt_skills, skills):
            raise AssertionError(
                f"student {split.student_id}: train+eval skills do not reconstruct history"
            )
        if not np.array_equal(rebuilt_correct, correct):
            raise AssertionError(
                f"student {split.student_id}: train+eval labels do not reconstruct history"
            )

        # The eval portion must be strictly the tail.
        if split.split_index + len(split.eval_skills) != len(skills):
            raise AssertionError(
                f"student {split.student_id}: eval portion is not the most recent tail"
            )
        if len(split.train_skills) != split.split_index:
            raise AssertionError(
                f"student {split.student_id}: train length disagrees with split index"
            )
