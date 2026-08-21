"""Tests for SHAP-based per-atom explainability."""

from __future__ import annotations

import numpy as np
import pytest

from drugsim_chem.fingerprints import compute_morgan_fingerprint
from drugsim_chem.parsing import parse_molecule
from drugsim_chem.pipeline import process_structure
from drugsim_predict.explainability import compute_atom_contributions
from drugsim_predict.model_registry import load_model_bundle

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


@pytest.fixture(scope="module")
def bundle():
    return load_model_bundle()


def _featurize(smiles: str, bundle):
    processed = process_structure(smiles, "smiles")
    mol = parse_molecule(processed.standardized_smiles)
    descriptors_vec = np.array([getattr(processed.descriptors, f) or 0.0 for f in bundle.descriptor_fields])
    fingerprint_vec = compute_morgan_fingerprint(mol)
    return mol, descriptors_vec, fingerprint_vec


class TestComputeAtomContributions:
    def test_additivity_holds(self, bundle) -> None:
        """base_value + sum(all descriptor and atom contributions) must
        reconstruct predict_proba for the positive class -- this is the
        exact property the default TreeExplainer algorithm FAILED on these
        models (see explainability.py's module docstring); this test is
        what would have caught that before it ever reached production."""
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        result = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)

        feature_vec = np.concatenate([desc_vec, fp_vec]).reshape(1, -1)
        actual_proba = bundle.sklearn_model.predict_proba(feature_vec)[0][1]

        total_atom = sum(a.contribution for a in result.atom_contributions)
        total_desc = sum(d.contribution for d in result.descriptor_contributions)
        reconstructed = result.base_value + total_atom + total_desc + result.absent_substructure_contribution

        assert reconstructed == pytest.approx(actual_proba, abs=1e-4)

    def test_absent_substructure_contribution_is_the_real_gap(self, bundle) -> None:
        """Without it, atom + descriptor contributions alone do NOT
        reconstruct predict_proba -- confirms this field is load-bearing,
        not a vestigial always-zero placeholder."""
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        result = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        assert result.absent_substructure_contribution != 0.0

    def test_atom_contributions_cover_every_atom(self, bundle) -> None:
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        result = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        assert len(result.atom_contributions) == mol.GetNumAtoms()
        assert [a.atom_index for a in result.atom_contributions] == list(range(mol.GetNumAtoms()))

    def test_descriptor_contributions_cover_every_descriptor(self, bundle) -> None:
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        result = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        assert [d.name for d in result.descriptor_contributions] == bundle.descriptor_fields
        for d, expected_value in zip(result.descriptor_contributions, desc_vec):
            assert d.value == pytest.approx(float(expected_value))

    def test_deterministic_across_repeated_calls(self, bundle) -> None:
        """Same molecule, same explanation every time -- required for the
        same reproducibility reason every other prediction field is."""
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        r1 = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        r2 = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        assert [a.contribution for a in r1.atom_contributions] == [a.contribution for a in r2.atom_contributions]
        assert r1.base_value == r2.base_value

    def test_positive_class_label_matches_bundle(self, bundle) -> None:
        mol, desc_vec, fp_vec = _featurize(ASPIRIN, bundle)
        result = compute_atom_contributions(mol, desc_vec, fp_vec, bundle.descriptor_fields, bundle)
        assert result.positive_class_label == bundle.positive_class_label
