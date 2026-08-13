"""Tests for measurement aggregation with discordance flags.

This is the direct implementation of an explicit rule: never silently average
conflicting measurements. TestDiscordanceIsNeverSilentlyResolved is the class
that matters most — it proves a discordant result is flagged and its
aggregated_value is never mistakable for a trustworthy training label.
"""

from __future__ import annotations

import pytest

from drugsim_quality.aggregation import aggregate_binary, aggregate_continuous

pytestmark = pytest.mark.unit


class TestSingleValue:
    def test_single_continuous_value_passes_through(self) -> None:
        result = aggregate_continuous([5.0], is_potency=True)
        assert result.aggregated_value == 5.0
        assert result.method == "single_value"
        assert result.is_discordant is False

    def test_single_binary_value_passes_through(self) -> None:
        result = aggregate_binary([True])
        assert result.aggregated_value == 1.0
        assert result.is_discordant is False


class TestPotencyGeometricMean:
    """Potency is log-normal — geometric mean, not arithmetic."""

    def test_geometric_mean_is_used_not_arithmetic(self) -> None:
        # Geometric mean of 1 and 100 is 10; arithmetic mean would be 50.5 —
        # a very different number, and arithmetic is the wrong one for potency.
        result = aggregate_continuous([1.0, 100.0], is_potency=True)
        assert result.aggregated_value == pytest.approx(10.0)
        assert result.method == "geometric_mean"

    def test_concordant_values_are_not_discordant(self) -> None:
        result = aggregate_continuous([10.0, 12.0, 11.0], is_potency=True)
        assert result.is_discordant is False

    def test_nonpositive_potency_value_raises(self) -> None:
        with pytest.raises(ValueError, match="strictly positive"):
            aggregate_continuous([10.0, -5.0], is_potency=True)

    def test_zero_potency_value_raises(self) -> None:
        with pytest.raises(ValueError, match="strictly positive"):
            aggregate_continuous([10.0, 0.0], is_potency=True)


class TestOtherContinuousMedian:
    """Non-potency continuous endpoints use the median."""

    def test_median_is_used(self) -> None:
        result = aggregate_continuous([1.0, 2.0, 100.0], is_potency=False)
        assert result.aggregated_value == 2.0
        assert result.method == "median"

    def test_median_is_robust_to_a_single_outlier(self) -> None:
        result = aggregate_continuous([5.0, 5.5, 6.0, 1000.0], is_potency=False)
        assert result.aggregated_value == pytest.approx(5.75)


class TestDiscordanceIsNeverSilentlyResolved:
    """The core guarantee: a discordant result is flagged, not smoothed over."""

    def test_100x_potency_spread_is_discordant(self) -> None:
        """The exact scenario named in Phase 1 Step 8 §3.3."""
        result = aggregate_continuous([1.0, 100.0], is_potency=True)
        assert result.is_discordant is True
        assert result.value_spread_log10 == pytest.approx(2.0)

    def test_exactly_at_threshold_is_not_discordant(self) -> None:
        """10x exactly (log10 spread == 1.0) is the boundary, not over it."""
        result = aggregate_continuous([1.0, 10.0], is_potency=True)
        assert result.value_spread_log10 == pytest.approx(1.0)
        assert result.is_discordant is False

    def test_just_over_threshold_is_discordant(self) -> None:
        result = aggregate_continuous([1.0, 10.001], is_potency=True)
        assert result.is_discordant is True

    def test_discordant_result_still_reports_a_value(self) -> None:
        """aggregated_value is populated even when discordant — inspectable,
        but the caller must check is_discordant before using it for training."""
        result = aggregate_continuous([1.0, 1000.0], is_potency=True)
        assert result.aggregated_value is not None
        assert result.is_discordant is True

    def test_negative_scale_quantity_uses_absolute_difference(self) -> None:
        """logD-like values: log10(max/min) is undefined when values can be
        negative, so discordance uses absolute difference on the same
        threshold instead."""
        result = aggregate_continuous([-1.0, 0.5], is_potency=False)
        assert result.value_spread_log10 == pytest.approx(1.5)
        assert result.is_discordant is True

    def test_small_negative_scale_spread_is_not_discordant(self) -> None:
        result = aggregate_continuous([1.2, 1.5], is_potency=False)
        assert result.is_discordant is False

    def test_custom_threshold_is_respected(self) -> None:
        result = aggregate_continuous([1.0, 5.0], is_potency=True, discordance_threshold_log10=0.5)
        assert result.is_discordant is True  # log10(5) ≈ 0.7 > 0.5


class TestBinaryMajorityVote:
    def test_clear_majority_positive(self) -> None:
        result = aggregate_binary([True, True, False])
        assert result.aggregated_value == 1.0
        assert result.is_discordant is False

    def test_clear_majority_negative(self) -> None:
        result = aggregate_binary([False, False, True])
        assert result.aggregated_value == 0.0
        assert result.is_discordant is False

    def test_exact_tie_is_discordant(self) -> None:
        """A tie must never be silently resolved as 'probably positive' or
        interpreted as a 50% probability."""
        result = aggregate_binary([True, False])
        assert result.is_discordant is True
        assert result.aggregated_value == 0.5

    def test_tie_with_more_observations_still_discordant(self) -> None:
        result = aggregate_binary([True, True, False, False])
        assert result.is_discordant is True

    def test_unanimous_is_not_discordant(self) -> None:
        result = aggregate_binary([True, True, True, True])
        assert result.is_discordant is False
        assert result.aggregated_value == 1.0


class TestEmptyInputRejected:
    def test_empty_continuous_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            aggregate_continuous([], is_potency=True)

    def test_empty_binary_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            aggregate_binary([])


class TestNSourceMeasurementsIsAccurate:
    def test_count_matches_input_length(self) -> None:
        result = aggregate_continuous([1.0, 2.0, 3.0, 4.0], is_potency=False)
        assert result.n_source_measurements == 4

    def test_binary_count_matches_input_length(self) -> None:
        result = aggregate_binary([True, False, True, True, False])
        assert result.n_source_measurements == 5
