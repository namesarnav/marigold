"""Tests for the per-student temporal split — the highest-risk leakage spot."""

import numpy as np
import pytest

from ml.config import SplitConfig
from ml.data.splits import (
    StudentSequence,
    assert_no_leakage,
    group_interactions_by_student,
    holdout_size,
    split_all_students,
    split_student_temporal,
    split_summary,
)

CONFIG = SplitConfig(holdout_n=10, max_holdout_fraction=0.5, min_train_interactions=5)


def make_sequence(student_id: int, n: int, seed: int = 0) -> StudentSequence:
    rng = np.random.default_rng(seed)
    return StudentSequence(
        student_id=student_id,
        skills=rng.integers(0, 20, size=n).astype(np.int64),
        correct=rng.integers(0, 2, size=n).astype(np.int8),
        order=np.arange(n, dtype=np.int64),
    )


# --- the core invariant ---------------------------------------------------

def test_heldout_interactions_never_appear_in_training():
    """The invariant the whole benchmark rests on.

    Checked by position, not by value: skill/correct pairs legitimately repeat
    within a student, so comparing values would produce false failures. The
    boundary index is what must hold.
    """
    sequences = [make_sequence(i, n=60, seed=i) for i in range(20)]
    splits = split_all_students(sequences, CONFIG)
    assert len(splits) == 20

    by_id = {s.student_id: s for s in sequences}
    for split in splits:
        original = by_id[split.student_id]
        n = len(original)
        n_eval = len(split.eval_skills)

        # Training is exactly the prefix, eval exactly the suffix.
        assert np.array_equal(split.train_skills, original.skills[: n - n_eval])
        assert np.array_equal(split.eval_skills, original.skills[n - n_eval :])
        assert np.array_equal(split.train_correct, original.correct[: n - n_eval])
        assert np.array_equal(split.eval_correct, original.correct[n - n_eval :])

        # No overlap in positions, and together they cover the history.
        assert len(split.train_skills) + n_eval == n
        assert split.split_index == n - n_eval


def test_eval_is_strictly_the_most_recent_tail():
    """Held-out interactions must be the newest ones, not a random slice."""
    n = 40
    seq = StudentSequence(
        student_id=1,
        skills=np.arange(n, dtype=np.int64),  # skill == position, so order is visible
        correct=np.ones(n, dtype=np.int8),
        order=np.arange(n, dtype=np.int64),
    )
    split = split_student_temporal(seq, CONFIG)

    assert split is not None
    # With holdout_n=10 the eval skills must be exactly positions 30..39.
    assert split.eval_skills.tolist() == list(range(30, 40))
    assert split.train_skills.tolist() == list(range(0, 30))
    # Every training position is strictly earlier than every eval position.
    assert split.train_skills.max() < split.eval_skills.min()


def test_split_respects_order_column_not_array_position():
    """Ordering comes from `order`, so shuffled input still splits temporally."""
    n = 30
    rng = np.random.default_rng(7)
    permutation = rng.permutation(n)

    seq = StudentSequence(
        student_id=1,
        # skills encode true chronological position
        skills=permutation.astype(np.int64),
        correct=np.ones(n, dtype=np.int8),
        # order matches skills, so sorting by order restores 0..n-1
        order=permutation.astype(np.int64),
    )
    split = split_student_temporal(seq, CONFIG)

    assert split is not None
    assert split.eval_skills.tolist() == list(range(20, 30))
    assert split.train_skills.tolist() == list(range(0, 20))


def test_ties_in_order_preserve_input_order():
    """All-equal order values (as in the ASSISTments mirror) must be stable.

    The benchmark mirror has every timestamp set to 0, so the sort is entirely
    ties. A non-stable sort would silently scramble each student's history.
    """
    n = 30
    seq = StudentSequence(
        student_id=1,
        skills=np.arange(n, dtype=np.int64),
        correct=np.ones(n, dtype=np.int8),
        order=np.zeros(n, dtype=np.int64),  # every timestamp identical
    )
    split = split_student_temporal(seq, CONFIG)

    assert split is not None
    assert split.train_skills.tolist() == list(range(0, 20))
    assert split.eval_skills.tolist() == list(range(20, 30))


# --- determinism ----------------------------------------------------------

def test_split_is_deterministic_across_repeated_calls():
    sequences = [make_sequence(i, n=45, seed=i) for i in range(10)]

    first = split_all_students(sequences, CONFIG)
    second = split_all_students(sequences, CONFIG)

    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert a.student_id == b.student_id
        assert a.split_index == b.split_index
        assert np.array_equal(a.train_skills, b.train_skills)
        assert np.array_equal(a.eval_skills, b.eval_skills)
        assert np.array_equal(a.train_correct, b.train_correct)
        assert np.array_equal(a.eval_correct, b.eval_correct)


def test_split_does_not_depend_on_global_random_state():
    """No hidden RNG: seeding differently must not change the split."""
    sequences = [make_sequence(i, n=45, seed=i) for i in range(5)]

    np.random.seed(1)
    first = split_all_students(sequences, CONFIG)
    np.random.seed(999)
    second = split_all_students(sequences, CONFIG)

    for a, b in zip(first, second):
        assert np.array_equal(a.eval_skills, b.eval_skills)
        assert a.split_index == b.split_index


# --- holdout sizing edge cases -------------------------------------------

@pytest.mark.parametrize(
    "n,expected",
    [
        (0, 0),      # nothing at all
        (1, 0),      # cannot split
        (5, 0),      # cap gives 2, leaving 3 < min_train_interactions=5 -> drop
        (10, 5),     # cap gives 5, leaving exactly min_train_interactions=5 -> keep
        (11, 5),     # int(11*0.5)=5, leaving 6
        (30, 10),    # comfortably above both limits
        (100, 10),   # fixed N, not a fraction
        (1000, 10),  # long histories do not dominate the eval set
    ],
)
def test_holdout_size_edge_cases(n, expected):
    assert holdout_size(n, CONFIG) == expected


def test_short_students_are_dropped_not_silently_mangled():
    sequences = [
        make_sequence(1, n=3),   # too short
        make_sequence(2, n=50),  # fine
        make_sequence(3, n=1),   # too short
    ]
    splits = split_all_students(sequences, CONFIG)

    assert [s.student_id for s in splits] == [2]


def test_fraction_cap_prevents_mostly_eval_students():
    """A 12-interaction student must not have 10 held out."""
    seq = make_sequence(1, n=12)
    split = split_student_temporal(seq, CONFIG)

    assert split is not None
    assert len(split.eval_skills) == 6  # capped at 12 * 0.5
    assert len(split.train_skills) == 6


def test_holdout_is_fixed_n_so_long_students_do_not_dominate():
    short = split_student_temporal(make_sequence(1, n=30), CONFIG)
    long = split_student_temporal(make_sequence(2, n=2000), CONFIG)

    assert len(short.eval_skills) == len(long.eval_skills) == 10


# --- the runtime guard ----------------------------------------------------

def test_assert_no_leakage_accepts_a_correct_split():
    sequences = [make_sequence(i, n=40, seed=i) for i in range(5)]
    splits = split_all_students(sequences, CONFIG)
    assert_no_leakage(sequences, splits)  # must not raise


def test_assert_no_leakage_catches_a_corrupted_boundary():
    """The guard must actually fire — a guard that never fails is decoration."""
    from dataclasses import replace

    sequences = [make_sequence(1, n=40)]
    splits = split_all_students(sequences, CONFIG)

    # Duplicate one interaction into both sides, the exact shape of a leak.
    bad = replace(
        splits[0],
        train_skills=np.concatenate([splits[0].train_skills, splits[0].eval_skills[:1]]),
        train_correct=np.concatenate(
            [splits[0].train_correct, splits[0].eval_correct[:1]]
        ),
    )

    with pytest.raises(AssertionError):
        assert_no_leakage(sequences, [bad])


# --- grouping -------------------------------------------------------------

def test_group_interactions_by_student_separates_students():
    student_ids = np.array([1, 1, 2, 2, 2, 1], dtype=np.int64)
    skills = np.array([10, 11, 20, 21, 22, 12], dtype=np.int64)
    correct = np.array([1, 0, 1, 1, 0, 1], dtype=np.int8)
    order = np.array([0, 1, 0, 1, 2, 2], dtype=np.int64)

    sequences = group_interactions_by_student(student_ids, skills, correct, order)

    assert [s.student_id for s in sequences] == [1, 2]
    assert sequences[0].skills.tolist() == [10, 11, 12]
    assert sequences[1].skills.tolist() == [20, 21, 22]


def test_split_summary_counts_match_the_splits():
    sequences = [make_sequence(i, n=40, seed=i) for i in range(4)]
    splits = split_all_students(sequences, CONFIG)
    summary = split_summary(splits)

    assert summary["students"] == 4
    assert summary["eval_interactions"] == 40  # 4 students x 10
    assert summary["train_interactions"] == 4 * 30
    assert 0.0 <= summary["eval_positive_rate"] <= 1.0


def test_split_summary_handles_empty_input():
    assert split_summary([])["students"] == 0
