"""Tests for the serving interface: ordering, cold-start routing, time decay.

Predictions are driven by a stub prior with hand-chosen values rather than a
trained model, so the expected ranking is known exactly and the test asserts on
ordering logic rather than on model quality.
"""

from datetime import datetime, timedelta

import pytest

from ml.config import ColdStartConfig, ForgettingConfig
from ml.inference.predict import (
    ForgettingRanker,
    HistoryUnavailable,
    Interaction,
    apply_forgetting,
    rank_concepts_by_forgetting_risk,
    set_ranker,
)
from ml.models.coldstart import ConceptPrior

NOW = datetime(2026, 9, 3, 12, 0, 0)

# No blend window: the routing branch under test should be unambiguous.
COLD = ColdStartConfig(min_interactions_for_sakt=20, blend_window=0, prior_strength=20.0)
# Decay disabled by an enormous half-life, so ordering tests isolate the prior.
NO_DECAY = ForgettingConfig(half_life_days=1e9, floor=0.0)


def make_ranker(concept_rates, forgetting=NO_DECAY, cold=COLD) -> ForgettingRanker:
    prior = ConceptPrior(
        global_rate=0.5,
        concept_rates=dict(concept_rates),
        # Large pseudo-count so a couple of user attempts do not perturb the
        # hand-chosen rates these tests depend on.
        prior_strength=1e6,
    )
    return ForgettingRanker(
        model=None,
        prior=prior,
        concept_to_skill={},
        cold_start_config=cold,
        forgetting_config=forgetting,
    )


# --- ordering -------------------------------------------------------------

def test_ranking_is_ascending_by_p_correct():
    """Highest forgetting risk (lowest P(correct)) must come first."""
    ranker = make_ranker({"easy": 0.9, "medium": 0.6, "hard": 0.2})

    scores = ranker.rank("u1", ["easy", "medium", "hard"], NOW, history=[])

    assert [s.concept_id for s in scores] == ["hard", "medium", "easy"]
    probs = [s.p_correct for s in scores]
    assert probs == sorted(probs)


def test_ranking_is_independent_of_input_order():
    ranker = make_ranker({"a": 0.1, "b": 0.5, "c": 0.9})

    forward = ranker.rank("u1", ["a", "b", "c"], NOW, history=[])
    reversed_ = ranker.rank("u1", ["c", "b", "a"], NOW, history=[])

    assert [s.concept_id for s in forward] == [s.concept_id for s in reversed_]


def test_ties_break_deterministically_on_concept_id():
    """Equal probabilities must still produce a stable, total order."""
    ranker = make_ranker({"zebra": 0.5, "apple": 0.5, "mango": 0.5})

    first = ranker.rank("u1", ["zebra", "apple", "mango"], NOW, history=[])
    second = ranker.rank("u1", ["mango", "zebra", "apple"], NOW, history=[])

    assert [s.concept_id for s in first] == ["apple", "mango", "zebra"]
    assert [s.concept_id for s in first] == [s.concept_id for s in second]


def test_public_function_returns_id_probability_pairs_in_rank_order():
    ranker = make_ranker({"x": 0.8, "y": 0.3})
    ranker.history_provider = lambda user_id: []
    set_ranker(ranker)
    try:
        result = rank_concepts_by_forgetting_risk("u1", ["x", "y"], NOW)
    finally:
        set_ranker(None)

    assert [c for c, _ in result] == ["y", "x"]
    assert all(isinstance(p, float) for _, p in result)


def test_public_function_uses_the_configured_history_provider():
    """The spec signature omits history, so it must be loaded, not assumed empty."""
    seen = {}

    def provider(user_id):
        seen["user_id"] = user_id
        return [Interaction("x", True, NOW - timedelta(days=400))]

    ranker = make_ranker(
        {"x": 0.9, "y": 0.5},
        forgetting=ForgettingConfig(half_life_days=7.0, floor=0.25),
    )
    ranker.history_provider = provider
    set_ranker(ranker)
    try:
        result = dict(rank_concepts_by_forgetting_risk("user-42", ["x", "y"], NOW))
    finally:
        set_ranker(None)

    assert seen["user_id"] == "user-42"
    # x was reviewed 400 days ago, so its 0.9 prior must have decayed below y.
    assert result["x"] < result["y"]


def test_public_function_raises_rather_than_silently_ranking_on_no_history():
    """A wrong answer that looks right is the failure mode worth preventing."""
    ranker = make_ranker({"x": 0.8})
    ranker.history_provider = None
    set_ranker(ranker)
    try:
        with pytest.raises(HistoryUnavailable, match="history_provider"):
            rank_concepts_by_forgetting_risk("u1", ["x"], NOW)
    finally:
        set_ranker(None)


def test_explicitly_passed_history_bypasses_the_provider():
    def exploding_provider(user_id):
        raise AssertionError("provider must not be called when history is passed")

    ranker = make_ranker({"x": 0.8})
    ranker.history_provider = exploding_provider
    set_ranker(ranker)
    try:
        result = rank_concepts_by_forgetting_risk("u1", ["x"], NOW, history=[])
    finally:
        set_ranker(None)

    assert result == [("x", pytest.approx(0.8))]


def test_empty_candidate_list_returns_empty():
    ranker = make_ranker({"a": 0.5})
    assert ranker.rank("u1", [], NOW, history=[]) == []


def test_unknown_concepts_fall_back_to_the_global_rate():
    ranker = make_ranker({"known": 0.9})
    scores = {s.concept_id: s.p_correct for s in
              ranker.rank("u1", ["known", "unknown"], NOW, history=[])}

    assert scores["unknown"] == pytest.approx(0.5)
    assert scores["known"] == pytest.approx(0.9)


# --- cold-start routing ---------------------------------------------------

def test_sparse_user_is_served_by_the_prior():
    ranker = make_ranker({"a": 0.7})
    history = [
        Interaction("a", True, NOW - timedelta(days=1)) for _ in range(3)
    ]

    scores = ranker.rank("u1", ["a"], NOW, history=history)

    assert scores[0].source == "prior"


def test_source_is_prior_when_no_model_is_loaded_even_for_heavy_users():
    """A missing checkpoint must degrade to the prior, not crash."""
    ranker = make_ranker({"a": 0.7})
    history = [Interaction("a", True, NOW - timedelta(days=1)) for _ in range(200)]

    scores = ranker.rank("u1", ["a"], NOW, history=history)

    assert scores[0].source == "prior"
    assert 0.0 <= scores[0].p_correct <= 1.0


def test_skipped_interactions_are_excluded_from_the_count():
    """A skip carries no evidence, so it must not push a user over the
    cold-start threshold or count as an attempt on the concept."""
    ranker = make_ranker({"a": 0.7})
    history = [Interaction("a", None, NOW - timedelta(days=1)) for _ in range(50)]

    scores = ranker.rank("u1", ["a"], NOW, history=history)

    assert scores[0].n_interactions_on_concept == 0
    assert scores[0].days_since_last_review is None


def test_graded_interactions_are_counted_per_concept():
    ranker = make_ranker({"a": 0.7, "b": 0.7})
    history = [
        Interaction("a", True, NOW - timedelta(days=3)),
        Interaction("a", False, NOW - timedelta(days=2)),
        Interaction("b", True, NOW - timedelta(days=1)),
        Interaction("a", None, NOW - timedelta(hours=1)),  # skip, ignored
    ]

    scores = {s.concept_id: s for s in ranker.rank("u1", ["a", "b"], NOW, history)}

    assert scores["a"].n_interactions_on_concept == 2
    assert scores["b"].n_interactions_on_concept == 1


# --- time decay -----------------------------------------------------------

def test_forgetting_decays_toward_the_floor_over_time():
    config = ForgettingConfig(half_life_days=7.0, floor=0.25)

    assert apply_forgetting(0.85, 0.0, config) == pytest.approx(0.85)
    # One half-life: halfway from 0.85 down to the 0.25 floor.
    assert apply_forgetting(0.85, 7.0, config) == pytest.approx(0.55)
    assert apply_forgetting(0.85, 14.0, config) == pytest.approx(0.40)
    # Far future approaches, but never crosses, the floor.
    assert apply_forgetting(0.85, 10_000.0, config) == pytest.approx(0.25, abs=1e-6)


def test_forgetting_is_monotonically_decreasing_in_elapsed_time():
    config = ForgettingConfig(half_life_days=7.0, floor=0.25)
    values = [apply_forgetting(0.9, d, config) for d in range(0, 60)]
    assert values == sorted(values, reverse=True)


def test_never_reviewed_concepts_are_not_decayed():
    config = ForgettingConfig(half_life_days=7.0, floor=0.25)
    assert apply_forgetting(0.8, None, config) == 0.8


def test_decay_output_stays_in_unit_interval():
    config = ForgettingConfig(half_life_days=7.0, floor=0.25)
    for p in (0.0, 0.1, 0.25, 0.5, 1.0):
        for days in (0, 1, 30, 365):
            assert 0.0 <= apply_forgetting(p, days, config) <= 1.0


def test_stale_concept_outranks_a_freshly_reviewed_one():
    """The product-level behaviour the decay exists to produce."""
    ranker = make_ranker(
        {"stale": 0.8, "fresh": 0.8},
        forgetting=ForgettingConfig(half_life_days=7.0, floor=0.25),
    )
    history = [
        Interaction("stale", True, NOW - timedelta(days=30)),
        Interaction("fresh", True, NOW - timedelta(hours=1)),
    ]

    scores = ranker.rank("u1", ["stale", "fresh"], NOW, history=history)

    assert [s.concept_id for s in scores] == ["stale", "fresh"]
    assert scores[0].p_correct < scores[1].p_correct


def test_as_of_in_the_future_projects_further_decay():
    """The exam-readiness hook: a future as_of must lower P(correct)."""
    ranker = make_ranker(
        {"a": 0.9}, forgetting=ForgettingConfig(half_life_days=7.0, floor=0.25)
    )
    history = [Interaction("a", True, NOW - timedelta(days=1))]

    today = ranker.rank("u1", ["a"], NOW, history=history)[0]
    exam_day = ranker.rank("u1", ["a"], NOW + timedelta(days=21), history=history)[0]

    assert exam_day.p_correct < today.p_correct
    assert exam_day.days_since_last_review > today.days_since_last_review


def test_days_since_last_review_uses_the_most_recent_interaction():
    ranker = make_ranker({"a": 0.7})
    history = [
        Interaction("a", True, NOW - timedelta(days=10)),
        Interaction("a", False, NOW - timedelta(days=2)),
    ]

    score = ranker.rank("u1", ["a"], NOW, history=history)[0]

    assert score.days_since_last_review == pytest.approx(2.0, abs=1e-6)


def test_history_order_does_not_affect_the_result():
    """Rows may arrive in any order; the ranker sorts them itself."""
    ranker = make_ranker({"a": 0.7})
    older = Interaction("a", True, NOW - timedelta(days=10))
    newer = Interaction("a", False, NOW - timedelta(days=2))

    forward = ranker.rank("u1", ["a"], NOW, history=[older, newer])[0]
    backward = ranker.rank("u1", ["a"], NOW, history=[newer, older])[0]

    assert forward.p_correct == pytest.approx(backward.p_correct)
    assert forward.days_since_last_review == pytest.approx(
        backward.days_since_last_review
    )


# --- the SAKT path through the ranker -------------------------------------
# The tests above all exercise the prior path (concept_to_skill={}). These
# cover the model path: index mapping, batching, and which position is read.

import numpy as np
import torch

from ml.config import SAKTConfig
from ml.models.sakt import SAKTModel

SAKT_TEST_CONFIG = SAKTConfig(max_seq_len=16, d_model=32, n_heads=4, ffn_hidden=32)


def make_sakt_ranker(n_skills=4, cold=COLD, forgetting=NO_DECAY):
    torch.manual_seed(0)
    model = SAKTModel(n_skills, SAKT_TEST_CONFIG)
    model.eval()
    return ForgettingRanker(
        model=model,
        prior=ConceptPrior(global_rate=0.5, concept_rates={}, prior_strength=1e6),
        concept_to_skill={f"c{i}": i for i in range(n_skills)},
        sakt_config=SAKT_TEST_CONFIG,
        cold_start_config=cold,
        forgetting_config=forgetting,
    )


def _history(n, concept="c0"):
    return [
        Interaction(concept, i % 2 == 0, NOW - timedelta(days=n - i))
        for i in range(n)
    ]


def test_sakt_path_is_taken_once_the_user_has_enough_history():
    ranker = make_sakt_ranker()
    scores = ranker.rank("u1", ["c0", "c1"], NOW, history=_history(30))

    assert all(s.source == "sakt" for s in scores)
    assert all(0.0 <= s.p_correct <= 1.0 for s in scores)


def test_prior_path_is_taken_below_the_threshold_even_with_a_model():
    ranker = make_sakt_ranker()
    scores = ranker.rank("u1", ["c0", "c1"], NOW, history=_history(5))

    assert all(s.source == "prior" for s in scores)


def test_sakt_predictions_differ_across_candidate_concepts():
    """Confirms the query index actually varies per candidate.

    A bug that wrote the same query for every row would produce identical
    probabilities and would otherwise look entirely healthy.
    """
    ranker = make_sakt_ranker()
    scores = ranker.rank("u1", ["c0", "c1", "c2", "c3"], NOW, history=_history(30))

    probs = [s.p_correct for s in scores]
    assert len(set(probs)) > 1


def test_sakt_predictions_are_deterministic():
    ranker = make_sakt_ranker()
    history = _history(30)

    first = ranker.rank("u1", ["c0", "c1"], NOW, history=history)
    second = ranker.rank("u1", ["c0", "c1"], NOW, history=history)

    assert [s.p_correct for s in first] == [s.p_correct for s in second]


def test_candidates_the_model_never_saw_fall_back_to_the_prior():
    """An unmapped concept must not be given an arbitrary skill index."""
    ranker = make_sakt_ranker()
    scores = {
        s.concept_id: s
        for s in ranker.rank("u1", ["c0", "brand-new"], NOW, history=_history(30))
    }

    assert scores["c0"].source == "sakt"
    assert scores["brand-new"].source == "prior"


def test_history_longer_than_max_seq_len_is_truncated_to_the_recent_window():
    ranker = make_sakt_ranker()
    long_history = _history(200)  # max_seq_len is 16

    scores = ranker.rank("u1", ["c0"], NOW, history=long_history)

    assert scores[0].source == "sakt"
    assert 0.0 <= scores[0].p_correct <= 1.0


def test_history_of_only_unmapped_concepts_falls_back_to_prior():
    ranker = make_sakt_ranker()
    history = [
        Interaction("unmapped", True, NOW - timedelta(days=i)) for i in range(30)
    ]

    scores = ranker.rank("u1", ["c0"], NOW, history=history)

    assert scores[0].source == "prior"


def test_sakt_output_still_gets_time_decay_applied():
    ranker = make_sakt_ranker(
        forgetting=ForgettingConfig(half_life_days=7.0, floor=0.25)
    )
    recent = _history(30)
    stale = [
        Interaction("c0", i % 2 == 0, NOW - timedelta(days=365 + 30 - i))
        for i in range(30)
    ]

    fresh_score = ranker.rank("u1", ["c0"], NOW, history=recent)[0]
    stale_score = ranker.rank("u1", ["c0"], NOW, history=stale)[0]

    assert stale_score.p_correct < fresh_score.p_correct
