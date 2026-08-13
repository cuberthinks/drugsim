"""Tests for split conformal prediction sets."""

from __future__ import annotations

import numpy as np
import pytest

from drugsim_predict.conformal import compute_conformal_set
from drugsim_predict.model_registry import load_model_bundle

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


@pytest.fixture(scope="module")
def bundle():
    return load_model_bundle()


class TestComputeConformalSet:
    def test_confident_blocker_prediction_yields_singleton_set(self, bundle) -> None:
        result = compute_conformal_set(np.array([0.02, 0.98]), bundle)
        assert result.predicted_set == ("blocker",)
        assert result.is_singleton is True

    def test_confident_non_blocker_prediction_yields_singleton_set(self, bundle) -> None:
        result = compute_conformal_set(np.array([0.98, 0.02]), bundle)
        assert result.predicted_set == ("non_blocker",)
        assert result.is_singleton is True

    def test_ambiguous_prediction_can_yield_both_classes(self, bundle) -> None:
        result = compute_conformal_set(np.array([0.5, 0.5]), bundle)
        # At a coin-flip probability, both labels are plausible at 90% confidence.
        assert set(result.predicted_set) == {"blocker", "non_blocker"}
        assert result.is_singleton is False

    def test_nominal_confidence_matches_bundle(self, bundle) -> None:
        result = compute_conformal_set(np.array([0.5, 0.5]), bundle)
        assert result.nominal_confidence == bundle.nominal_confidence

    def test_p_values_are_valid_probabilities(self, bundle) -> None:
        result = compute_conformal_set(np.array([0.3, 0.7]), bundle)
        assert 0.0 <= result.p_value_blocker <= 1.0
        assert 0.0 <= result.p_value_non_blocker <= 1.0

    def test_calibration_nonconformity_scores_are_in_valid_range(self, bundle) -> None:
        """Nonconformity = 1 - P(true class), so every frozen score must
        lie in [0, 1] -- a corrupted or mistakenly-rebuilt calibration
        artifact would show up here as an out-of-range value."""
        assert (bundle.calibration_nonconformity >= 0.0).all()
        assert (bundle.calibration_nonconformity <= 1.0).all()
        assert bundle.calibration_nonconformity.shape[0] > 500

    def test_higher_predicted_probability_yields_higher_p_value_for_that_class(self, bundle) -> None:
        """Monotonicity sanity check: a higher P(blocker) means LOWER
        nonconformity for the "blocker" hypothesis (alpha = 1 - P), which
        means MORE calibration points exceed it, which means a HIGHER
        p-value -- i.e. stronger evidence keeps "blocker" in the set more
        easily, not less."""
        weak = compute_conformal_set(np.array([0.4, 0.6]), bundle)
        strong = compute_conformal_set(np.array([0.1, 0.9]), bundle)
        assert strong.p_value_blocker >= weak.p_value_blocker
