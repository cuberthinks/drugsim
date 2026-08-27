"""Tests for the explainable data-quality score.

The property that matters most: discordance drops both the score and
eligibility, but never makes a compound disappear — the score still
computes, on real components, for an ineligible compound.
"""

from __future__ import annotations

import pytest

from drugsim_curation.quality_score import QUALITY_SCORE_WEIGHTS, compute_quality_score

pytestmark = pytest.mark.unit


class TestWeightsSumToOne:
    def test_weights_sum_to_one(self) -> None:
        assert sum(QUALITY_SCORE_WEIGHTS.values()) == pytest.approx(1.0)


class TestPerfectRecordScoresNearMaximum:
    def test_all_ones_scores_one(self) -> None:
        result = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=1.0,
            duplicate_resolution=1.0,
            assay_context_coverage=1.0,
            provenance_completeness=1.0,
        )
        assert result.total == pytest.approx(1.0)


class TestDiscordanceDropsScoreButStillComputes:
    def test_discordant_compound_gets_a_real_lower_score_not_a_missing_one(self) -> None:
        consistent = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=1.0,
            duplicate_resolution=1.0,
            assay_context_coverage=1.0,
            provenance_completeness=1.0,
        )
        discordant = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=0.0,  # the only thing that changed
            duplicate_resolution=1.0,
            assay_context_coverage=1.0,
            provenance_completeness=1.0,
        )
        assert discordant.total < consistent.total
        assert discordant.total == pytest.approx(consistent.total - QUALITY_SCORE_WEIGHTS["measurement_consistency"])
        # The score is a real number, not None or omitted -- an ineligible
        # compound is still fully described, never hidden.
        assert isinstance(discordant.total, float)


class TestPartialAssayCoverageIsAFraction:
    def test_partial_coverage_scores_between_full_and_none(self) -> None:
        partial = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=1.0,
            duplicate_resolution=1.0,
            assay_context_coverage=0.5,
            provenance_completeness=1.0,
        )
        full = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=1.0,
            duplicate_resolution=1.0,
            assay_context_coverage=1.0,
            provenance_completeness=1.0,
        )
        none = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=1.0,
            license_resolution=1.0,
            measurement_consistency=1.0,
            duplicate_resolution=1.0,
            assay_context_coverage=0.0,
            provenance_completeness=1.0,
        )
        assert none.total < partial.total < full.total


class TestBreakdownExposesEveryComponent:
    def test_each_component_matches_what_was_passed_in(self) -> None:
        inputs = {
            "structure_validity": 0.25,
            "unit_resolution_rate": 0.5,
            "license_resolution": 0.75,
            "measurement_consistency": 1.0,
            "duplicate_resolution": 0.9,
            "assay_context_coverage": 0.1,
            "provenance_completeness": 0.0,
        }
        result = compute_quality_score(**inputs)
        for name, value in inputs.items():
            assert getattr(result, name) == pytest.approx(value)

    def test_total_is_reconstructable_by_hand_from_the_breakdown(self) -> None:
        inputs = {
            "structure_validity": 0.25,
            "unit_resolution_rate": 0.5,
            "license_resolution": 0.75,
            "measurement_consistency": 1.0,
            "duplicate_resolution": 0.9,
            "assay_context_coverage": 0.1,
            "provenance_completeness": 0.0,
        }
        result = compute_quality_score(**inputs)
        manual_total = sum(getattr(result, name) * weight for name, weight in QUALITY_SCORE_WEIGHTS.items())
        assert result.total == pytest.approx(manual_total)
