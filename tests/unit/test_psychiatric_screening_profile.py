"""Tests for the multi-objective psychiatric screening profile.

Runs the real offline artifacts (DRD2/HRH1/CYP2D6/BBB/hERG models
already committed to this checkout when run in CI/dev, since they are
gitignored data -- see conftest skip behaviour) against two real
reference compounds with well-documented, opposite pharmacology,
verifying the profile's STRUCTURE and honesty guarantees rather than
re-asserting exact model outputs (those are already pinned in each
endpoint's own evaluation_report.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

MODELS_PSYCHIATRIC = Path(__file__).resolve().parents[2] / "models" / "psychiatric"
sys.path.insert(0, str(MODELS_PSYCHIATRIC))

_ARTIFACTS_PRESENT = all(
    (MODELS_PSYCHIATRIC / endpoint / "artifact" / "model.joblib").exists()
    for endpoint in ("drd2_activity", "hrh1_activity", "cyp2d6_activity", "bbb_permeability")
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not _ARTIFACTS_PRESENT,
        reason="Model artifacts are gitignored binaries -- only present after running each endpoint's own train.py locally.",
    ),
]

HALOPERIDOL_SMILES = "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1"
DIPHENHYDRAMINE_SMILES = "CN(C)CCOC(c1ccccc1)c1ccccc1"


@pytest.fixture(scope="module")
def haloperidol_profile():
    from screening_profile import screen_compound

    return screen_compound(HALOPERIDOL_SMILES)


@pytest.fixture(scope="module")
def diphenhydramine_profile():
    from screening_profile import screen_compound

    return screen_compound(DIPHENHYDRAMINE_SMILES)


class TestProfileStructure:
    def test_every_endpoint_is_present(self, haloperidol_profile) -> None:
        p = haloperidol_profile
        assert p.drd2 is not None
        assert p.hrh1 is not None
        assert p.cyp2d6 is not None
        assert p.bbb is not None
        assert p.herg is not None

    def test_selectivity_is_derived_from_the_two_regression_signals(self, haloperidol_profile) -> None:
        p = haloperidol_profile
        expected = round(p.drd2.predicted_pki - p.hrh1.predicted_pki, 4)
        assert p.selectivity_index_log10 == pytest.approx(expected, abs=1e-3)


class TestReliabilityTierHonesty:
    """The whole point of this module: never claim equal reliability across endpoints."""

    def test_herg_is_reported_as_validated(self, haloperidol_profile) -> None:
        assert haloperidol_profile.herg.reliability_tier == "validated"

    def test_cyp2d6_and_bbb_are_reported_as_experimental(self, haloperidol_profile) -> None:
        p = haloperidol_profile
        assert p.cyp2d6.reliability_tier == "experimental"
        assert p.bbb.reliability_tier == "experimental"

    def test_drd2_and_hrh1_are_reported_as_experimental(self, haloperidol_profile) -> None:
        p = haloperidol_profile
        assert p.drd2.reliability_tier == "experimental"
        assert p.hrh1.reliability_tier == "experimental"

    def test_overall_caveats_warn_against_treating_signals_as_equally_reliable(self, haloperidol_profile) -> None:
        joined = " ".join(haloperidol_profile.overall_caveats).lower()
        assert "do not treat all six signals as equally trustworthy" in joined


class TestRealPharmacologyDirectionalSanity:
    """Cross-checks against well-established, independently-documented pharmacology.

    Not exact-value assertions (those live in each endpoint's own
    evaluation_report.json) -- these check DIRECTION only, the same
    correctness signal demo_selectivity.py already established for
    DRD2/HRH1/Selectivity, now extended across all six endpoints.
    """

    def test_haloperidol_is_predicted_more_drd2_selective_than_hrh1_selective(self, haloperidol_profile) -> None:
        assert haloperidol_profile.selectivity_index_log10 > 0

    def test_diphenhydramine_is_predicted_more_hrh1_selective_than_drd2_selective(self, diphenhydramine_profile) -> None:
        assert diphenhydramine_profile.selectivity_index_log10 < 0

    def test_haloperidol_is_flagged_bbb_permeant(self, haloperidol_profile) -> None:
        assert haloperidol_profile.bbb.predicted_label == "bbb_permeant"

    def test_diphenhydramine_is_flagged_bbb_permeant(self, diphenhydramine_profile) -> None:
        assert diphenhydramine_profile.bbb.predicted_label == "bbb_permeant"
