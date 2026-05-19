"""Tests for the cold-start threshold and the population prior."""

import pytest

from ml.config import ColdStartConfig
from ml.models.coldstart import (
    ConceptPrior,
    blend,
    fit_concept_prior,
    sakt_blend_weight,
    should_use_sakt,
)

CONFIG = ColdStartConfig(
    min_interactions_for_sakt=20, blend_window=20, prior_strength=20.0
)
HARD_SWITCH = ColdStartConfig(
    min_interactions_for_sakt=20, blend_window=0, prior_strength=20.0
)


# --- the threshold switch -------------------------------------------------

@pytest.mark.parametrize(
    "count,expected",
    [
        (0, False),
        (1, False),
        (19, False),   # just below
        (20, True),    # exactly at the threshold -> SAKT
        (21, True),
        (5000, True),
    ],
)
def test_should_use_sakt_boundary(count, expected):
    assert should_use_sakt(count, CONFIG) is expected


def test_threshold_is_inclusive_at_the_configured_value():
    """Pinning the boundary semantics: >= threshold, not > threshold."""
    assert should_use_sakt(CONFIG.min_interactions_for_sakt, CONFIG) is True
    assert should_use_sakt(CONFIG.min_interactions_for_sakt - 1, CONFIG) is False


def test_threshold_respects_a_custom_config():
    strict = ColdStartConfig(min_interactions_for_sakt=100)
    assert should_use_sakt(50, strict) is False
    assert should_use_sakt(100, strict) is True


def test_negative_counts_do_not_enable_sakt():
    assert should_use_sakt(-5, CONFIG) is False


# --- blend weighting ------------------------------------------------------

def test_blend_weight_is_zero_below_threshold():
    for count in (0, 10, 19):
        assert sakt_blend_weight(count, CONFIG) == 0.0


def test_blend_weight_ramps_then_saturates():
    assert sakt_blend_weight(20, CONFIG) == 0.0     # at threshold, ramp starts
    assert sakt_blend_weight(30, CONFIG) == pytest.approx(0.5)
    assert sakt_blend_weight(40, CONFIG) == 1.0     # window complete
    assert sakt_blend_weight(999, CONFIG) == 1.0    # stays saturated


def test_blend_weight_is_monotonic():
    weights = [sakt_blend_weight(n, CONFIG) for n in range(0, 60)]
    assert weights == sorted(weights)


def test_blend_weight_never_leaves_unit_interval():
    for n in range(0, 200):
        assert 0.0 <= sakt_blend_weight(n, CONFIG) <= 1.0


def test_hard_switch_when_blend_window_is_zero():
    """blend_window=0 is the documented v1 hard-switch behaviour."""
    assert sakt_blend_weight(19, HARD_SWITCH) == 0.0
    assert sakt_blend_weight(20, HARD_SWITCH) == 1.0


def test_blend_weight_and_should_use_sakt_never_disagree():
    """A nonzero SAKT weight must imply the threshold was passed."""
    for n in range(0, 100):
        if sakt_blend_weight(n, CONFIG) > 0.0:
            assert should_use_sakt(n, CONFIG)


# --- combining predictions ------------------------------------------------

def test_blend_uses_prior_when_sakt_is_unavailable():
    value, source = blend(0.8, None, user_interaction_count=500, config=CONFIG)
    assert value == 0.8
    assert source == "prior"


def test_blend_uses_prior_below_threshold():
    value, source = blend(0.8, 0.2, user_interaction_count=5, config=CONFIG)
    assert value == 0.8
    assert source == "prior"


def test_blend_uses_sakt_once_the_window_completes():
    value, source = blend(0.8, 0.2, user_interaction_count=40, config=CONFIG)
    assert value == 0.2
    assert source == "sakt"


def test_blend_interpolates_inside_the_window():
    value, source = blend(1.0, 0.0, user_interaction_count=30, config=CONFIG)
    assert value == pytest.approx(0.5)
    assert source == "blend"


def test_blend_output_lies_between_its_inputs():
    for n in range(0, 60):
        value, _ = blend(0.9, 0.1, user_interaction_count=n, config=CONFIG)
        assert 0.1 <= value <= 0.9


# --- the population prior -------------------------------------------------

def test_prior_shrinks_sparse_concepts_toward_the_global_rate():
    """Two observations must not produce a 0.0 or 1.0 estimate."""
    observations = [("easy", True)] * 100 + [("hard", False)] * 100
    observations += [("sparse", True), ("sparse", True)]

    prior = fit_concept_prior(observations, CONFIG)

    assert prior.predict("sparse") < 0.9
    assert prior.predict("sparse") > prior.global_rate
    # Well-observed concepts are allowed to move far from the mean.
    assert prior.predict("easy") > 0.7
    assert prior.predict("hard") < 0.3


def test_prior_falls_back_to_global_rate_for_unknown_concepts():
    prior = fit_concept_prior([("a", True), ("a", False)], CONFIG)
    assert prior.predict("never-seen") == prior.global_rate


def test_prior_with_no_data_is_maximally_uncertain():
    prior = fit_concept_prior([], CONFIG)
    assert prior.global_rate == 0.5
    assert prior.predict("anything") == 0.5


def test_prior_estimates_stay_in_unit_interval():
    observations = [("all-right", True)] * 50 + [("all-wrong", False)] * 50
    prior = fit_concept_prior(observations, CONFIG)

    for concept in ("all-right", "all-wrong", "unknown"):
        assert 0.0 <= prior.predict(concept) <= 1.0


def test_user_evidence_moves_the_estimate_in_the_right_direction():
    prior = fit_concept_prior([("c", True), ("c", False)] * 50, CONFIG)
    base = prior.predict("c")

    better = prior.predict_for_user("c", user_correct=10, user_attempts=10)
    worse = prior.predict_for_user("c", user_correct=0, user_attempts=10)

    assert better > base
    assert worse < base


def test_user_evidence_with_no_attempts_returns_the_bare_prior():
    prior = fit_concept_prior([("c", True)] * 10, CONFIG)
    assert prior.predict_for_user("c", 0, 0) == prior.predict("c")


def test_prior_round_trips_through_serialisation(tmp_path):
    prior = fit_concept_prior([("a", True), ("a", False), ("b", True)], CONFIG)
    path = tmp_path / "prior.json"
    prior.save(path)

    restored = ConceptPrior.load(path)

    assert restored.global_rate == pytest.approx(prior.global_rate)
    assert restored.predict("a") == pytest.approx(prior.predict("a"))
    assert restored.predict("b") == pytest.approx(prior.predict("b"))
    assert restored.prior_strength == prior.prior_strength


def test_fit_counts_every_observation():
    prior = fit_concept_prior([("a", True), ("a", False), ("b", True)], CONFIG)
    assert prior.concept_counts == {"a": 2, "b": 1}
