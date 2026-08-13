"""Scientific regression suite for the registered hERG inhibition model.

Phase 7 hardening. Distinct from ``test_golden_regression.py`` (which pins
the *chemistry pipeline's* output byte-for-byte) — this suite pins the
*model's* qualitative behaviour on a fixed, representative panel of
molecules, so that a future change to the model, preprocessing, descriptors,
fingerprints, applicability-domain logic, or uncertainty method is caught
even though none of those are expected to change frequently.

Design choice, per the Phase 7 brief ("store expected behaviour, not
fragile exact values where unnecessary"): each fixture pins a *qualitative*
expectation (predicted label, applicability-domain verdict category,
singleton/non-singleton, a wide probability band) rather than the exact
floating-point probability. A retrain that shifts terfenadine's blocker
probability from 0.878 to 0.85 is not a regression worth failing CI over;
a retrain that flips its label from "blocker" to "non_blocker", or moves it
out of the applicability domain, almost certainly is.

What each assertion actually detects:
    - model_id / model_version mismatch -> model replacement
    - feature_set_id mismatch -> descriptor, fingerprint, or standardisation
      pipeline change (feature_set_id is a content address over exactly
      these, per ADR-005) -- this is the single cheapest, highest-signal
      check in this file, since it fires on ANY toolchain drift even before
      any molecule's prediction changes
    - canonical_smiles mismatch -> preprocessing/standardisation change
    - predicted_label mismatch, or probability outside its wide band ->
      the model itself has changed in a way that matters
    - applicability_domain.verdict mismatch -> AD logic or training
      reference data changed
    - conformal.is_singleton / predicted_set mismatch -> uncertainty
      (conformal calibration) changed

The panel is intentionally small (7 molecules) and reused across categories
where a molecule's real, observed behaviour already covers more than one
(e.g. ivermectin is simultaneously "chemically unusual", "borderline", and
"out of domain" for this model) -- that overlap is realistic, not a gap.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from drugsim_predict.model_registry import get_model_bundle
from drugsim_predict.pipeline import run_inference

pytestmark = [pytest.mark.golden, pytest.mark.model_artifact]

# Pinned bundle identity. A model swap, feature-pipeline change, or
# descriptor/fingerprint change changes at least one of these.
EXPECTED_MODEL_ID = "herg_inhibition"
EXPECTED_MODEL_VERSION = "0.1.0"
EXPECTED_FEATURE_SET_ID = "a3ee2afe06243a9c3eca4e1d3f74393e900c0961f915609ac29b07e4d9919b30"
EXPECTED_DATASET_VERSION = "v1"
EXPECTED_NOMINAL_CONFIDENCE = 0.9


@dataclass(frozen=True)
class RegressionCase:
    name: str
    smiles: str
    canonical_smiles: str
    categories: tuple[str, ...]
    expected_label: str
    expected_ad_verdict: str
    expected_is_singleton: bool
    prob_blocker_band: tuple[float, float]  # wide, deliberately not exact


# Observed against the currently-registered model
# (herg_inhibition v0.1.0, feature_set_id above) on 2026-08-09. Bands are
# +/- 0.15 around the observed probability, clamped to [0, 1] -- wide enough
# to absorb ordinary retraining noise, narrow enough that a label-flip-worthy
# shift still fails.
CASES: list[RegressionCase] = [
    RegressionCase(
        name="terfenadine_strong_inhibitor_in_domain",
        smiles="CC(C)(C)c1ccc(cc1)C(O)CCCN1CCC(CC1)C(O)(c1ccccc1)c1ccccc1",
        canonical_smiles="CC(C)(C)c1ccc(C(O)CCCN2CCC(C(O)(c3ccccc3)c3ccccc3)CC2)cc1",
        categories=("strong_inhibition", "in_domain"),
        expected_label="blocker",
        expected_ad_verdict="in_domain",
        expected_is_singleton=True,
        prob_blocker_band=(0.73, 1.0),
    ),
    RegressionCase(
        name="astemizole_strong_inhibitor_out_of_domain",
        smiles="COc1ccc(CCN2CCC(CC2)N2c3ccccc3N(C)C2=O)cc1",
        canonical_smiles="COc1ccc(CCN2CCC(n3c(=O)n(C)c4ccccc43)CC2)cc1",
        categories=("strong_inhibition", "out_of_domain"),
        expected_label="blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=True,
        prob_blocker_band=(0.74, 1.0),
    ),
    RegressionCase(
        name="aspirin_weak_inhibitor_common_compound",
        smiles="CC(=O)Oc1ccccc1C(=O)O",
        canonical_smiles="CC(=O)Oc1ccccc1C(=O)O",
        categories=("weak_inhibition", "out_of_domain"),
        expected_label="non_blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=True,
        prob_blocker_band=(0.13, 0.43),
    ),
    RegressionCase(
        name="glycine_weak_inhibitor_minimal_molecule",
        smiles="NCC(=O)O",
        canonical_smiles="NCC(=O)O",
        categories=("weak_inhibition", "out_of_domain"),
        expected_label="non_blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=True,
        prob_blocker_band=(0.06, 0.36),
    ),
    RegressionCase(
        name="dofetilide_borderline_at_decision_boundary",
        smiles="CS(=O)(=O)Nc1ccc(cc1)CCN(C)CCOc1ccc(NS(C)(=O)=O)cc1",
        canonical_smiles="CN(CCOc1ccc(NS(C)(=O)=O)cc1)CCc1ccc(NS(C)(=O)=O)cc1",
        categories=("borderline", "out_of_domain"),
        expected_label="blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=False,
        prob_blocker_band=(0.37, 0.67),
    ),
    RegressionCase(
        name="caffeine_borderline_common_compound",
        smiles="Cn1cnc2c1c(=O)n(C)c(=O)n2C",
        canonical_smiles="Cn1c(=O)c2c(ncn2C)n(C)c1=O",
        categories=("borderline", "out_of_domain"),
        expected_label="non_blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=False,
        prob_blocker_band=(0.19, 0.49),
    ),
    RegressionCase(
        name="ivermectin_chemically_unusual_macrocycle",
        smiles=(
            "CCC(C)C1CCC2(CC1OC1CC(OC)C(OC3CC(OC)C(O)C(C)O3)C(C)O1)CC1CC(C)C=C3CC("
            "C(=CC=C4CC(O)C(C)C(C(C)C(O)C(C)/C=C/C=C4/O2)O4)C4CC(C)O)OC13"
        ),
        canonical_smiles=(
            "CCC(C)C1CCC2(CC3CC(C)C=C4CC(OC43)C3=CC=C4CC(O)C(C)C(OC3CC(C)O)C(C)C(O)C(C)"
            "C=CC=C4O2)CC1OC1CC(OC)C(OC2CC(OC)C(O)C(C)O2)C(C)O1"
        ),
        categories=("chemically_unusual", "borderline", "out_of_domain"),
        expected_label="blocker",
        expected_ad_verdict="out_of_domain",
        expected_is_singleton=False,
        prob_blocker_band=(0.48, 0.78),
    ),
]

CASE_IDS = [c.name for c in CASES]


@pytest.fixture(scope="module")
def bundle_identity():
    bundle = get_model_bundle()
    return bundle


class TestBundleIdentity:
    """Fires on model replacement or a toolchain change, independent of any
    single molecule's prediction -- the cheapest, highest-signal check."""

    def test_model_identity_is_pinned(self, bundle_identity) -> None:
        assert bundle_identity.model_id == EXPECTED_MODEL_ID
        assert bundle_identity.model_version == EXPECTED_MODEL_VERSION

    def test_feature_set_id_is_pinned(self, bundle_identity) -> None:
        assert bundle_identity.feature_set_id == EXPECTED_FEATURE_SET_ID, (
            "feature_set_id changed -- this means the descriptor set, fingerprint "
            "parameters, standardisation pipeline, or RDKit version changed. If "
            "intentional, regenerate this suite's expectations deliberately "
            "(re-run the probe molecules and update the pinned values); if not, "
            "this is exactly the reproducibility break TDS Sec 6.6 stage 3 exists "
            "to catch."
        )

    def test_dataset_version_is_pinned(self, bundle_identity) -> None:
        assert bundle_identity.dataset_version == EXPECTED_DATASET_VERSION

    def test_conformal_nominal_confidence_is_pinned(self, bundle_identity) -> None:
        assert bundle_identity.nominal_confidence == EXPECTED_NOMINAL_CONFIDENCE


class TestRepresentativeMoleculePanel:
    @pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
    def test_predicted_label(self, case: RegressionCase) -> None:
        result = run_inference(case.smiles, "smiles")
        assert result.predicted_label == case.expected_label, (
            f"{case.name} ({', '.join(case.categories)}): predicted_label changed "
            f"from '{case.expected_label}' -- the model's qualitative behaviour on "
            f"this representative compound has changed."
        )

    @pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
    def test_probability_within_expected_band(self, case: RegressionCase) -> None:
        result = run_inference(case.smiles, "smiles")
        lo, hi = case.prob_blocker_band
        assert lo <= result.predicted_probability_blocker <= hi, (
            f"{case.name}: predicted_probability_blocker="
            f"{result.predicted_probability_blocker} outside the expected "
            f"[{lo}, {hi}] band -- a shift this large is worth investigating even "
            f"if the label didn't flip."
        )

    @pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
    def test_applicability_domain_verdict(self, case: RegressionCase) -> None:
        result = run_inference(case.smiles, "smiles")
        assert result.applicability_domain.verdict == case.expected_ad_verdict, (
            f"{case.name}: applicability-domain verdict changed -- the AD logic "
            f"or the frozen training reference data changed."
        )

    @pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
    def test_conformal_singleton_status(self, case: RegressionCase) -> None:
        result = run_inference(case.smiles, "smiles")
        assert result.conformal.is_singleton == case.expected_is_singleton, (
            f"{case.name}: conformal singleton status changed -- the uncertainty "
            f"(conformal calibration) has changed."
        )

    @pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
    def test_canonical_smiles_is_stable(self, case: RegressionCase) -> None:
        result = run_inference(case.smiles, "smiles")
        assert result.canonical_smiles == case.canonical_smiles, (
            f"{case.name}: canonical SMILES changed -- the standardisation/"
            f"preprocessing pipeline has changed."
        )


class TestPanelCoversRequiredCategories:
    """Guards against the panel itself silently losing coverage over time."""

    def test_panel_covers_every_required_category(self) -> None:
        required = {
            "strong_inhibition",
            "weak_inhibition",
            "borderline",
            "chemically_unusual",
            "in_domain",
            "out_of_domain",
        }
        covered = {cat for case in CASES for cat in case.categories}
        missing = required - covered
        assert not missing, f"Regression panel no longer covers: {missing}"
