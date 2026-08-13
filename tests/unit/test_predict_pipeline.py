"""Tests for the core inference pipeline.

Covers valid/invalid inputs, standardisation consistency, feature
generation consistency, and regression against known reference molecules
-- the set explicitly required by the Phase 5 brief.
"""

from __future__ import annotations

import numpy as np
import pytest

from drugsim_core.errors import StructureError
from drugsim_predict.model_registry import load_model_bundle
from drugsim_predict.pipeline import run_inference

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
# A textbook, extensively documented hERG blocker structure (terfenadine-class
# diphenhydramine/piperidinol scaffold) -- used throughout this project's own
# training data with high potency; a real regression anchor, not a synthetic one.
KNOWN_BLOCKER_LIKE = "CC(C)(C)c1ccc(cc1)C(O)CCCN1CCC(CC1)C(O)(c1ccccc1)c1ccccc1"


@pytest.fixture(scope="module")
def bundle():
    return load_model_bundle()


class TestValidInputs:
    def test_aspirin_produces_a_complete_result(self, bundle) -> None:
        result = run_inference(ASPIRIN, bundle=bundle)
        assert result.predicted_label in ("blocker", "non_blocker")
        assert 0.0 <= result.predicted_probability_blocker <= 1.0
        assert result.applicability_domain is not None
        assert result.conformal is not None

    def test_result_always_has_full_reliability_info(self, bundle) -> None:
        """No code path may produce a result missing conformal or AD data --
        the dataclass has no Optional there, but assert the actual values
        are populated, not just present-but-None-shaped."""
        result = run_inference(ASPIRIN, bundle=bundle)
        assert result.conformal.predicted_set
        assert result.applicability_domain.verdict in (
            "in_domain", "borderline", "out_of_domain", "undeterminable",
        )

    def test_molblock_and_inchi_formats_are_accepted(self, bundle) -> None:
        # A minimal valid V2000 molblock for ethanol.
        molblock = (
            "\n     RDKit          2D\n\n"
            "  3  2  0  0  0  0  0  0  0  0999 V2000\n"
            "    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "    1.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "    2.0000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0\n"
            "  1  2  1  0\n  2  3  1  0\nM  END\n"
        )
        result = run_inference(molblock, fmt="molblock", bundle=bundle)
        assert result.molecular_formula == "C2H6O"

        inchi_result = run_inference("InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3", fmt="inchi", bundle=bundle)
        assert inchi_result.molecular_formula == "C2H6O"


class TestInvalidInputs:
    def test_empty_structure_rejected(self, bundle) -> None:
        with pytest.raises(StructureError):
            run_inference("", bundle=bundle)

    def test_whitespace_only_structure_rejected(self, bundle) -> None:
        with pytest.raises(StructureError):
            run_inference("   ", bundle=bundle)

    def test_malformed_smiles_rejected(self, bundle) -> None:
        with pytest.raises(StructureError):
            run_inference("C(C(C(", bundle=bundle)

    def test_oversized_structure_rejected(self, bundle) -> None:
        with pytest.raises(StructureError):
            run_inference("C" * 6000, bundle=bundle)

    def test_mixture_with_no_dominant_fragment_rejected(self, bundle) -> None:
        with pytest.raises(StructureError, match="mixture"):
            run_inference("CCO.CCN", bundle=bundle)

    def test_wildcard_atom_rejected(self, bundle) -> None:
        with pytest.raises(StructureError):
            run_inference("CC(*)CC", bundle=bundle)

    def test_high_molecular_weight_rejected(self, bundle) -> None:
        # A long-chain polyethylene-glycol-like structure comfortably over 2000 Da.
        huge = "C" + "OCC" * 200
        with pytest.raises(StructureError, match="molecular weight"):
            run_inference(huge, bundle=bundle)


class TestStandardizationConsistency:
    def test_equivalent_smiles_produce_identical_canonical_form(self, bundle) -> None:
        a = run_inference("CCO", bundle=bundle)
        b = run_inference("OCC", bundle=bundle)
        assert a.canonical_smiles == b.canonical_smiles
        assert a.inchikey_full == b.inchikey_full

    def test_repeated_calls_are_deterministic(self, bundle) -> None:
        r1 = run_inference(ASPIRIN, bundle=bundle)
        r2 = run_inference(ASPIRIN, bundle=bundle)
        assert r1.canonical_smiles == r2.canonical_smiles
        assert r1.predicted_label == r2.predicted_label
        assert r1.predicted_probability_blocker == r2.predicted_probability_blocker
        assert r1.applicability_domain.verdict == r2.applicability_domain.verdict
        assert r1.conformal.predicted_set == r2.conformal.predicted_set


class TestFeatureGenerationConsistency:
    def test_feature_set_id_matches_bundle(self, bundle) -> None:
        result = run_inference(ASPIRIN, bundle=bundle)
        assert result.feature_set_id == bundle.feature_set_id

    def test_prediction_matches_directly_computed_model_output(self, bundle) -> None:
        """The pipeline's own feature computation, run end to end, must
        produce the exact class probability the model itself would give a
        directly-computed feature vector -- i.e. pipeline.py does not
        silently transform or reorder anything the model wasn't trained on."""
        from drugsim_chem import compute_morgan_fingerprint, process_structure
        from drugsim_chem.parsing import parse_molecule

        processed = process_structure(ASPIRIN)
        mol = parse_molecule(processed.standardized_smiles)
        descriptors_vec = np.array([getattr(processed.descriptors, f) or 0.0 for f in bundle.descriptor_fields])
        fingerprint_vec = compute_morgan_fingerprint(mol)
        feature_vec = np.concatenate([descriptors_vec, fingerprint_vec]).reshape(1, -1)
        expected_prob = bundle.sklearn_model.predict_proba(feature_vec)[0][1]

        result = run_inference(ASPIRIN, bundle=bundle)
        assert result.predicted_probability_blocker == round(float(expected_prob), 4)


class TestRegressionAgainstKnownMolecules:
    """Pinned expectations for two well-characterised reference compounds.
    A change to these values on an unrelated commit is a regression, not
    routine drift -- investigate before updating (same policy as
    tests/golden/test_golden_regression.py)."""

    def test_aspirin_is_predicted_non_blocker(self, bundle) -> None:
        """Aspirin has no established hERG liability in the literature."""
        result = run_inference(ASPIRIN, bundle=bundle)
        assert result.predicted_label == "non_blocker"

    def test_known_blocker_like_structure_is_predicted_blocker(self, bundle) -> None:
        """A diphenhydramine/piperidinol-scaffold structure closely related
        to well-documented hERG-blocking antihistamines."""
        result = run_inference(KNOWN_BLOCKER_LIKE, bundle=bundle)
        assert result.predicted_label == "blocker"
        assert result.applicability_domain.verdict == "in_domain"
