"""Tests for window construction and the SAKT input framing.

The split (test_splits.py) guarantees held-out interactions never enter
training. These tests guarantee the second half of the no-leakage story: that
within a window, the answer being predicted is not visible in the input.
"""

import numpy as np
import pytest
import torch

from ml.config import SAKTConfig, SplitConfig
from ml.data.sequences import (
    PAD_ID,
    build_eval_windows,
    build_train_windows,
    encode_interaction,
)
from ml.data.splits import StudentSequence, split_all_students, split_student_temporal
from ml.models.sakt import SAKTModel, positional_sanity_check

SPLIT_CONFIG = SplitConfig(holdout_n=5, max_holdout_fraction=0.5, min_train_interactions=5)
SAKT_CONFIG = SAKTConfig(max_seq_len=16, d_model=32, n_heads=4, ffn_hidden=32)
N_SKILLS = 10


def make_split(n=30, seed=0):
    rng = np.random.default_rng(seed)
    seq = StudentSequence(
        student_id=1,
        skills=rng.integers(0, N_SKILLS, size=n).astype(np.int64),
        correct=rng.integers(0, 2, size=n).astype(np.int8),
        order=np.arange(n, dtype=np.int64),
    )
    return seq, split_student_temporal(seq, SPLIT_CONFIG)


# --- the interaction encoding --------------------------------------------

def test_encode_interaction_separates_correct_from_incorrect():
    skills = np.array([0, 0, 3, 3], dtype=np.int64)
    correct = np.array([0, 1, 0, 1], dtype=np.int64)

    encoded = encode_interaction(skills, correct, N_SKILLS)

    # Same skill, different outcome -> different embedding index.
    assert encoded[0] != encoded[1]
    assert encoded[2] != encoded[3]
    # Nothing collides with the padding index.
    assert (encoded != PAD_ID).all()


def test_encode_interaction_is_injective_over_the_id_space():
    skills = np.repeat(np.arange(N_SKILLS), 2)
    correct = np.tile(np.array([0, 1]), N_SKILLS)

    encoded = encode_interaction(skills, correct.astype(np.int64), N_SKILLS)

    assert len(np.unique(encoded)) == len(encoded)
    assert encoded.min() >= 1
    assert encoded.max() <= 2 * N_SKILLS


# --- the one-step offset, which is what prevents self-leakage ------------

def test_window_inputs_are_offset_one_step_behind_the_targets():
    """past_interactions[i] describes step i; the target is step i+1.

    This offset is the structural guarantee that a position's own answer is not
    among its inputs. Asserted directly against a known sequence.
    """
    n = 12
    skills = np.arange(n, dtype=np.int64) % N_SKILLS
    correct = (np.arange(n) % 2).astype(np.int8)
    seq = StudentSequence(1, skills, correct, np.arange(n, dtype=np.int64))
    split = split_student_temporal(seq, SPLIT_CONFIG)

    windows = build_train_windows([split], N_SKILLS, SAKT_CONFIG)
    assert windows

    w = windows[0]
    train_skills = split.train_skills
    train_correct = split.train_correct
    length = len(train_skills) - 1

    expected_past = encode_interaction(
        train_skills[:length], train_correct[:length].astype(np.int64), N_SKILLS
    )
    assert w.past_interactions[:length].tolist() == expected_past.tolist()
    assert w.query_skills[:length].tolist() == (train_skills[1:] + 1).tolist()
    assert w.targets[:length].tolist() == train_correct[1:].astype(int).tolist()


def test_target_answer_is_not_encoded_at_its_own_input_position():
    """Flip one answer and confirm only *later* inputs change.

    If the label leaked into its own position, changing the answer at step k
    would change past_interactions at the index that predicts step k.
    """
    n = 14
    skills = np.zeros(n, dtype=np.int64)
    correct = np.zeros(n, dtype=np.int8)
    seq_a = StudentSequence(1, skills, correct, np.arange(n, dtype=np.int64))

    flipped = correct.copy()
    flipped[7] = 1
    seq_b = StudentSequence(1, skills, flipped, np.arange(n, dtype=np.int64))

    wa = build_train_windows([split_student_temporal(seq_a, SPLIT_CONFIG)], N_SKILLS, SAKT_CONFIG)[0]
    wb = build_train_windows([split_student_temporal(seq_b, SPLIT_CONFIG)], N_SKILLS, SAKT_CONFIG)[0]

    # The prediction for step 7 is made at index 6. Its input must be identical.
    assert wa.past_interactions[6] == wb.past_interactions[6]
    assert wa.targets[6] != wb.targets[6]  # the label did change
    # The change shows up only from index 7 onward, which the causal mask hides.
    assert wa.past_interactions[7] != wb.past_interactions[7]


# --- eval windows ---------------------------------------------------------

def test_eval_windows_score_only_heldout_positions():
    seq, split = make_split(n=30)
    windows = build_eval_windows([split], N_SKILLS, SAKT_CONFIG)

    total_scored = sum(int(w.score_mask.sum()) for w in windows)
    assert total_scored == len(split.eval_skills)


def test_eval_window_targets_at_scored_positions_are_the_heldout_labels():
    seq, split = make_split(n=30, seed=3)
    windows = build_eval_windows([split], N_SKILLS, SAKT_CONFIG)

    scored_targets = np.concatenate(
        [w.targets[w.score_mask.astype(bool)] for w in windows]
    )
    assert scored_targets.tolist() == split.eval_correct.astype(int).tolist()


def test_eval_windows_use_training_history_as_context():
    """Context is allowed and expected — but only from earlier positions."""
    seq, split = make_split(n=30)
    windows = build_eval_windows([split], N_SKILLS, SAKT_CONFIG)

    w = windows[0]
    # More positions exist than are scored: the extras are context.
    assert int(w.score_mask.sum()) < int((w.query_skills != PAD_ID).sum())


def test_train_windows_never_contain_heldout_interactions():
    """Belt and braces: train windows are built from the train split only."""
    n = 40
    skills = np.arange(n, dtype=np.int64) % N_SKILLS
    # Mark held-out steps with a distinctive correctness pattern we can detect.
    correct = np.zeros(n, dtype=np.int8)
    correct[-5:] = 1
    seq = StudentSequence(1, skills, correct, np.arange(n, dtype=np.int64))
    split = split_student_temporal(seq, SPLIT_CONFIG)

    windows = build_train_windows([split], N_SKILLS, SAKT_CONFIG)

    # No training target may be 1, since only held-out steps were marked 1.
    for w in windows:
        assert w.targets[w.score_mask.astype(bool)].sum() == 0


def test_long_histories_are_chunked_not_truncated():
    """Every interaction must appear; none silently dropped past max_seq_len."""
    n = 100  # far beyond max_seq_len=16
    seq, split = make_split(n=n)
    windows = build_train_windows([split], N_SKILLS, SAKT_CONFIG)

    total_scored = sum(int(w.score_mask.sum()) for w in windows)
    # Every training step except the very first is predicted exactly once.
    assert total_scored == len(split.train_skills) - 1


def test_windows_are_padded_to_the_configured_length():
    seq, split = make_split(n=30)
    for w in build_train_windows([split], N_SKILLS, SAKT_CONFIG):
        assert len(w.past_interactions) == SAKT_CONFIG.max_seq_len
        assert len(w.query_skills) == SAKT_CONFIG.max_seq_len
        assert len(w.targets) == SAKT_CONFIG.max_seq_len
        assert len(w.score_mask) == SAKT_CONFIG.max_seq_len


def test_padding_positions_are_never_scored():
    seq, split = make_split(n=23)
    for w in build_train_windows([split], N_SKILLS, SAKT_CONFIG):
        padded = w.query_skills == PAD_ID
        assert (w.score_mask[padded] == 0).all()


def test_single_interaction_student_produces_no_windows():
    """Nothing precedes the first step, so it can never be predicted."""
    seq = StudentSequence(
        1,
        np.array([3], dtype=np.int64),
        np.array([1], dtype=np.int8),
        np.array([0], dtype=np.int64),
    )
    from ml.data.splits import TemporalSplit

    split = TemporalSplit(
        student_id=1,
        train_skills=seq.skills,
        train_correct=seq.correct,
        eval_skills=np.array([], dtype=np.int64),
        eval_correct=np.array([], dtype=np.int8),
        split_index=1,
    )
    assert build_train_windows([split], N_SKILLS, SAKT_CONFIG) == []


# --- the causal mask ------------------------------------------------------

def test_causal_mask_blocks_the_future_but_allows_the_present():
    mask = SAKTModel.causal_mask(4, torch.device("cpu"))

    # True == disallowed. Diagonal must be allowed: key i precedes query i.
    assert not mask[0, 0] and not mask[3, 3]
    assert not mask[3, 0]  # can look back
    assert mask[0, 1] and mask[0, 3]  # cannot look forward


def test_model_predictions_do_not_depend_on_future_inputs():
    torch.manual_seed(0)
    model = SAKTModel(N_SKILLS, SAKT_CONFIG)
    positional_sanity_check(model)  # must not raise


def test_sanity_check_fires_when_the_mask_is_disabled():
    """The guard must be capable of failing, or it proves nothing."""
    torch.manual_seed(0)
    model = SAKTModel(N_SKILLS, SAKT_CONFIG)

    # Replace the causal mask with an all-allowed mask, simulating the bug.
    model.causal_mask = staticmethod(
        lambda seq_len, device: torch.zeros(
            seq_len, seq_len, dtype=torch.bool, device=device
        )
    )

    with pytest.raises(AssertionError):
        positional_sanity_check(model)


# --- empirical leakage check ---------------------------------------------

@pytest.mark.slow
def test_random_labels_yield_chance_auc():
    """Train briefly on labels with no signal; AUC must stay near 0.5.

    This is the strongest available end-to-end evidence that the pipeline does
    not leak. If any part of the framing exposed a target to its own input, the
    model could fit pure noise and AUC would rise well above chance.
    """
    from sklearn.metrics import roc_auc_score

    from ml.data.sequences import make_loader

    rng = np.random.default_rng(0)
    n_students, n_steps = 120, 40

    sequences = [
        StudentSequence(
            student_id=i,
            skills=rng.integers(0, N_SKILLS, size=n_steps).astype(np.int64),
            # Labels independent of everything: pure coin flips.
            correct=rng.integers(0, 2, size=n_steps).astype(np.int8),
            order=np.arange(n_steps, dtype=np.int64),
        )
        for i in range(n_students)
    ]
    splits = split_all_students(sequences, SPLIT_CONFIG)

    train_windows = build_train_windows(splits, N_SKILLS, SAKT_CONFIG)
    eval_windows = build_eval_windows(splits, N_SKILLS, SAKT_CONFIG)

    torch.manual_seed(0)
    model = SAKTModel(N_SKILLS, SAKT_CONFIG)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = torch.nn.BCEWithLogitsLoss()

    loader = make_loader(train_windows, batch_size=32, shuffle=False)
    model.train()
    for _ in range(5):
        for past, query, target, mask in loader:
            logits = model(past, query)
            if mask.sum() == 0:
                continue
            loss = criterion(logits[mask], target[mask])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    model.eval()
    probs, targets = [], []
    with torch.no_grad():
        for past, query, target, mask in make_loader(
            eval_windows, batch_size=32, shuffle=False
        ):
            logits = model(past, query)
            probs.append(torch.sigmoid(logits[mask]).numpy())
            targets.append(target[mask].numpy())

    auc = roc_auc_score(np.concatenate(targets), np.concatenate(probs))

    # Generous band: this is a small sample, so chance AUC has real variance.
    # The point is to catch leakage, which would push this toward 0.9+.
    assert 0.35 < auc < 0.65, f"AUC {auc:.3f} on random labels suggests leakage"
