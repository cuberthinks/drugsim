"""Tests for the empirical unit-verification protocol (gate G4).

TestSignInversionDetection is the most important class here: it proves the
protocol actually catches the LD50-style sign inversion Phase 1 flagged as the
highest-risk conversion in the system, and proves that range/skewness checks
CANNOT catch it alone — only the reference-compound check can, which is the
whole reason it exists as a separate method.
"""

from __future__ import annotations

import pytest

from drugsim_quality.unit_verification import (
    ReferenceCompoundCheck,
    verify_range,
    verify_reference_compounds,
    verify_skewness_consistent_with_log_scale,
)

pytestmark = pytest.mark.unit


class TestVerifyRange:
    def test_values_within_envelope_pass(self) -> None:
        result = verify_range([1.0, 2.0, 3.0], expected_min=0, expected_max=10)
        assert result.passed is True

    def test_values_far_outside_envelope_fail(self) -> None:
        result = verify_range([100, 200, 300], expected_min=0, expected_max=10)
        assert result.passed is False

    def test_a_few_outliers_within_tolerance_still_pass(self) -> None:
        values = [1.0] * 95 + [1000.0] * 5  # 5% outliers
        result = verify_range(values, expected_min=0, expected_max=10, tolerance_fraction=0.05)
        assert result.passed is True

    def test_empty_values_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            verify_range([], expected_min=0, expected_max=1)

    def test_detail_is_always_populated(self) -> None:
        result = verify_range([1.0], expected_min=0, expected_max=10)
        assert result.detail


class TestSkewnessCheck:
    """Distribution shape as a unit-scale sanity check."""

    def test_symmetric_data_consistent_with_log_scale_claim(self) -> None:
        # Roughly symmetric around a central value.
        values = [-2, -1, -0.5, 0, 0.5, 1, 2]
        result = verify_skewness_consistent_with_log_scale(values, assumed_log_scale=True)
        assert result.passed is True

    def test_heavily_skewed_data_inconsistent_with_log_scale_claim(self) -> None:
        """A handful of extreme outliers stretching one tail — the shape a
        raw (non-log) concentration mislabelled as log-scale would have."""
        values = [1.0] * 20 + [1000.0, 5000.0, 10000.0]
        result = verify_skewness_consistent_with_log_scale(values, assumed_log_scale=True)
        assert result.passed is False

    def test_linear_scale_claim_never_fails_this_check(self) -> None:
        """Skewed data is EXPECTED for a linear-scale endpoint — this
        direction is not an error signal."""
        values = [1.0] * 20 + [1000.0, 5000.0, 10000.0]
        result = verify_skewness_consistent_with_log_scale(values, assumed_log_scale=False)
        assert result.passed is True

    def test_too_few_values_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 3"):
            verify_skewness_consistent_with_log_scale([1.0, 2.0], assumed_log_scale=True)

    def test_zero_variance_raises_rather_than_claiming_zero_skew(self) -> None:
        with pytest.raises(ValueError, match="undefined"):
            verify_skewness_consistent_with_log_scale([5.0, 5.0, 5.0], assumed_log_scale=True)


class TestReferenceCompounds:
    def test_matching_reference_values_pass(self) -> None:
        checks = [ReferenceCompoundCheck("caffeine_logs", expected_value=-1.4, observed_value=-1.3)]
        result = verify_reference_compounds(checks)
        assert result.passed is True

    def test_grossly_mismatched_values_fail(self) -> None:
        checks = [ReferenceCompoundCheck("caffeine_logs", expected_value=-1.4, observed_value=8.0)]
        result = verify_reference_compounds(checks)
        assert result.passed is False

    def test_one_failure_among_several_fails_the_whole_check(self) -> None:
        checks = [
            ReferenceCompoundCheck("compound_a", expected_value=1.0, observed_value=1.0),
            ReferenceCompoundCheck("compound_b", expected_value=1.0, observed_value=100.0),
        ]
        result = verify_reference_compounds(checks)
        assert result.passed is False
        assert "compound_b" in result.detail

    def test_empty_checks_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            verify_reference_compounds([])


class TestSignInversionDetection:
    """The reason verify_reference_compounds exists as a distinct method:
    range and skewness checks CANNOT distinguish a sign-inverted scale from a
    correct one, because negating a distribution preserves both its range
    membership (if symmetric around the check bounds) and its skewness
    magnitude (only the sign of skew flips, and |skew| is what both checks
    above threshold on)."""

    def test_range_check_cannot_detect_a_sign_inversion(self) -> None:
        """A correctly-scaled and a sign-inverted version of the same
        symmetric-envelope data both pass the range check — proving range
        alone is insufficient to catch this failure mode."""
        correct = [-3.0, -2.0, -1.0, 0.0, 1.0]
        inverted = [3.0, 2.0, 1.0, 0.0, -1.0]
        correct_result = verify_range(correct, expected_min=-5, expected_max=5)
        inverted_result = verify_range(inverted, expected_min=-5, expected_max=5)
        assert correct_result.passed is True
        assert inverted_result.passed is True  # <-- both pass; range can't tell them apart

    def test_reference_compound_check_detects_the_same_inversion(self) -> None:
        """The same inversion IS caught here: a known-toxic reference
        compound's inverted value falls far outside tolerance."""
        # Suppose LD50 is truly low (toxic) for this compound; the sign
        # inversion reports it as if it were high (safe) by the same margin.
        checks_correct = [ReferenceCompoundCheck("known_toxic", expected_value=5.0, observed_value=5.0)]
        checks_inverted = [ReferenceCompoundCheck("known_toxic", expected_value=5.0, observed_value=-5.0)]
        assert verify_reference_compounds(checks_correct).passed is True
        assert verify_reference_compounds(checks_inverted).passed is False
