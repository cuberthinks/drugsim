"""Tests for the DRD2/HRH1 selectivity calculation.

Pure function, no model/network needed -- exercises the direction-
correct math and uncertainty/domain handling directly. See
docs/psychiatric-pipeline/selectivity-methodology.md for the full
rationale this pins down.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "models" / "psychiatric"))

from selectivity import compute_selectivity  # noqa: E402

pytestmark = pytest.mark.unit


def _selectivity(pki_drd2: float, pki_hrh1: float, **overrides):
    defaults = dict(
        drd2_uncertainty_half_width=0.5,
        hrh1_uncertainty_half_width=0.5,
        drd2_in_domain=True,
        hrh1_in_domain=True,
    )
    defaults.update(overrides)
    return compute_selectivity(pki_drd2, pki_hrh1, **defaults)


class TestDirectionIsCorrect:
    """The whole point of this module: never a direction-ambiguous ratio."""

    def test_stronger_drd2_binding_gives_a_positive_index(self) -> None:
        # pki=8 means Ki=10nM; pki=6 means Ki=1000nM -- DRD2 binds 100x stronger.
        result = _selectivity(pki_drd2=8.0, pki_hrh1=6.0)
        assert result.selectivity_index_log10 > 0
        assert result.fold_selectivity_for_drd2 == pytest.approx(100.0, rel=1e-3)

    def test_stronger_hrh1_binding_gives_a_negative_index(self) -> None:
        result = _selectivity(pki_drd2=6.0, pki_hrh1=8.0)
        assert result.selectivity_index_log10 < 0
        assert result.fold_selectivity_for_drd2 == pytest.approx(0.01, rel=1e-3)

    def test_equal_binding_gives_zero(self) -> None:
        result = _selectivity(pki_drd2=7.0, pki_hrh1=7.0)
        assert result.selectivity_index_log10 == 0.0
        assert result.fold_selectivity_for_drd2 == pytest.approx(1.0)

    def test_the_index_is_never_a_raw_ratio_of_potency_values(self) -> None:
        """The exact bug the brief itself warned against: computing on raw Ki
        (smaller=stronger) instead of pKi (larger=stronger) flips the sign."""
        # DRD2 binds far more strongly (pKi 9 = Ki 1nM) than HRH1 (pKi 5 = Ki 100000nM).
        result = _selectivity(pki_drd2=9.0, pki_hrh1=5.0)
        # A correct result must say DRD2-selective (positive), not the reverse.
        assert result.selectivity_index_log10 > 0
        assert "DRD2" in result.interpretation
        assert "more strongly" in result.interpretation


class TestUncertaintyPropagation:
    def test_combined_uncertainty_is_the_sum_not_a_smaller_combination(self) -> None:
        result = _selectivity(pki_drd2=8.0, pki_hrh1=6.0, drd2_uncertainty_half_width=0.6, hrh1_uncertainty_half_width=0.9)
        assert result.uncertainty_half_width_log10 == pytest.approx(1.5)


class TestApplicabilityDomainHandling:
    def test_both_in_domain_reports_in_domain_status(self) -> None:
        result = _selectivity(8.0, 6.0, drd2_in_domain=True, hrh1_in_domain=True)
        assert result.domain_status == "in_domain"
        assert result.domain_caveat is None

    def test_either_target_out_of_domain_flags_the_whole_result(self) -> None:
        result = _selectivity(8.0, 6.0, drd2_in_domain=True, hrh1_in_domain=False)
        assert result.domain_status == "out_of_domain"
        assert result.domain_caveat is not None
        # The value must still be computed and returned, never hidden.
        assert result.selectivity_index_log10 == pytest.approx(2.0)

    def test_missing_domain_information_is_reported_as_unknown_not_assumed_in_domain(self) -> None:
        result = _selectivity(8.0, 6.0, drd2_in_domain=None, hrh1_in_domain=True)
        assert result.domain_status == "unknown"


class TestNoOverclaiming:
    def test_interpretation_never_mentions_safety_or_efficacy_as_a_conclusion(self) -> None:
        result = _selectivity(8.0, 6.0)
        lowered = result.interpretation.lower()
        assert "not a claim about clinical efficacy" in lowered or "not a claim about" in lowered
        assert "safe" not in lowered.replace("not a claim about clinical efficacy, safety", "")

    def test_interpretation_disclaims_weight_gain_causation(self) -> None:
        result = _selectivity(6.0, 9.0)
        assert "weight gain" in result.interpretation.lower()
        assert "multiple contributing mechanisms" in result.interpretation.lower()
