"""Tests for drug-likeness rule evaluation.

Every rule is a heuristic (Phase 1 Step 4 §7.1) — these tests check that the
computation is correct and internally consistent, not that any particular
molecule "should" pass any particular rule in some absolute sense.
"""

from __future__ import annotations

import pytest

from drugsim_chem.descriptors import compute_descriptors
from drugsim_chem.drug_likeness import assess_drug_likeness
from drugsim_chem.parsing import parse_molecule

pytestmark = pytest.mark.unit


def _assess(smiles: str, **kwargs: object):
    mol = parse_molecule(smiles)
    descriptors = compute_descriptors(mol)
    return assess_drug_likeness(mol, descriptors, **kwargs)


class TestLipinski:
    def test_aspirin_passes(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert result.lipinski_violations == 0
        assert result.lipinski_pass is True

    def test_pass_threshold_is_at_most_one_violation(self) -> None:
        """lipinski_pass = violations <= 1, not violations == 0 — a molecule
        with exactly one violation still passes per the standard rule.

        Quaterphenyl carboxylic acid verified empirically (not assumed) to
        have exactly one violation: LogP=6.39 (>5), while MW=350.4 (<=500),
        HBD=1 (<=5), HBA=2 (<=10) all comply.
        """
        one_violation = _assess("c1ccc(cc1)c1ccc(cc1)c1ccc(cc1)c1ccc(cc1)C(=O)O")
        assert one_violation.lipinski_violations == 1
        assert one_violation.lipinski_pass is True

    def test_violations_is_internally_consistent_with_pass(self) -> None:
        for smiles in ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"]:
            result = _assess(smiles)
            assert result.lipinski_pass == (result.lipinski_violations <= 1)


class TestVeber:
    def test_aspirin_passes_veber(self) -> None:
        assert _assess("CC(=O)Oc1ccccc1C(=O)O").veber_pass is True


class TestRuleOfThree:
    """Fragment-likeness — small, low-complexity molecules should pass."""

    def test_ethanol_passes_rule_of_three(self) -> None:
        assert _assess("CCO").rule_of_three_pass is True

    def test_aspirin_fails_rule_of_three(self) -> None:
        """Aspirin is small but exceeds Ro3's acceptor-count threshold under
        the literal Lipinski convention (hba_lipinski=4) — verified directly,
        not assumed."""
        assert _assess("CC(=O)Oc1ccccc1C(=O)O").rule_of_three_pass is False


class TestQedAndSaScore:
    """Bounded-range sanity checks — these are RDKit's own scores, not
    reimplemented, so the tests confirm correct wiring, not the science."""

    def test_qed_is_in_valid_range(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert 0 <= result.qed_score <= 1

    def test_sa_score_is_in_valid_range(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert 1 <= result.sa_score <= 10

    def test_simple_molecule_scores_more_synthetically_accessible_than_complex(self) -> None:
        simple = _assess("CCO").sa_score
        complex_steroid_like = _assess(
            "CC1=CC(=O)C2(C(C1)C3CCC4(C(C3(CC2O)C)CCC5(C4CC(C5(C)C(=O)O)O)C)C)C"
        ).sa_score
        assert simple < complex_steroid_like


class TestAlerts:
    def test_pains_alert_count_is_non_negative(self) -> None:
        assert _assess("CC(=O)Oc1ccccc1C(=O)O").pains_alerts >= 0

    def test_known_pains_scaffold_is_flagged(self) -> None:
        """A rhodanine core is a textbook PAINS-flagged chemotype."""
        result = _assess("O=C1CSC(=S)N1")
        assert result.pains_alerts >= 1

    def test_brenk_alert_count_is_non_negative(self) -> None:
        assert _assess("CC(=O)Oc1ccccc1C(=O)O").brenk_alerts >= 0


class TestBioavailabilityScore:
    """Martin (2005) heuristic — corrected during Sprint 2.5 (see
    drug_likeness.py docstring). Five tiers, not four: anions are scored by
    TPSA (0.85/0.56/0.11); neutral/zwitterionic/cationic compounds are scored
    by Lipinski Ro5 pass/fail (0.55/0.17), independent of TPSA."""

    def test_score_is_one_of_the_five_real_tiers(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert result.bioavailability_score in {0.11, 0.17, 0.55, 0.56, 0.85}

    def test_neutral_ro5_pass_gets_055(self) -> None:
        """Neutral compounds are scored by Ro5 pass/fail, NOT by TPSA —
        octane is neutral and passes Ro5, so it gets 0.55, not a TPSA-tier
        value (it has zero TPSA, which is irrelevant to this branch)."""
        result = _assess("CCCCCCCC")
        assert result.bioavailability_score == 0.55

    def test_neutral_ro5_fail_gets_017(self) -> None:
        """A large, non-anionic molecule failing Ro5 lands in the 0.17 tier.

        Verified empirically: MW=563, LogP=15.8, giving 2 Lipinski violations
        (fails, since the pass threshold is <=1).
        """
        result = _assess("CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC")
        assert result.lipinski_pass is False
        assert result.bioavailability_score == 0.17

    def test_anion_with_low_tpsa_gets_top_tier_085(self) -> None:
        """The tier the original (wrong) 4-value guess omitted entirely."""
        result = _assess("CC(=O)[O-]")  # acetate anion, TPSA=37.3 (<=75)
        assert result.bioavailability_score == 0.85

    def test_anion_with_mid_tpsa_gets_056(self) -> None:
        # Verified empirically: TPSA=77.4, charge=-1 (75 < TPSA < 150).
        result = _assess("O=C([O-])c1ccccc1C(=O)O")
        assert result.bioavailability_score == 0.56

    def test_anion_with_high_tpsa_gets_lowest_tier_011(self) -> None:
        # Verified empirically: TPSA=160.5, charge=-4 (TPSA >= 150).
        result = _assess("O=C([O-])c1cc(C(=O)[O-])c(C(=O)[O-])cc1C(=O)[O-]")
        assert result.bioavailability_score == 0.11


class TestPfizerFlagRequiresLogD:
    """pfizer_3_75_flag needs logD (measured/predicted), never a computed
    descriptor — Phase 1 Step 4 §1 correction. Must be None, not a guess,
    when unavailable."""

    def test_flag_is_none_without_logd(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert result.pfizer_3_75_flag is None

    def test_flag_is_computed_when_logd_provided(self) -> None:
        result = _assess("c1ccccc1CCCCCCCC", logd_74=4.0)
        assert result.pfizer_3_75_flag is not None
        assert isinstance(result.pfizer_3_75_flag, bool)


class TestGskFlagIsNamedFlagNotPass:
    """Naming discipline (Phase 1 Step 4 §7): _flag marks elevated risk, not
    failure — a downstream developer must not be able to assume _pass
    semantics by pattern-matching the field name."""

    def test_field_exists_and_is_boolean(self) -> None:
        result = _assess("CC(=O)Oc1ccccc1C(=O)O")
        assert isinstance(result.gsk_4_400_flag, bool)


class TestDeterminism:
    def test_repeated_assessment_is_identical(self) -> None:
        assert _assess("CC(=O)Oc1ccccc1C(=O)O") == _assess("CC(=O)Oc1ccccc1C(=O)O")
