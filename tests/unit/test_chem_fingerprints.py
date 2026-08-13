"""Tests for Morgan fingerprint computation."""

from __future__ import annotations

import numpy as np
import pytest

from drugsim_chem.fingerprints import compute_morgan_fingerprint
from drugsim_chem.parsing import parse_molecule

pytestmark = pytest.mark.unit


class TestComputeMorganFingerprint:
    def test_default_shape_and_dtype(self) -> None:
        fp = compute_morgan_fingerprint(parse_molecule("CCO"))
        assert fp.shape == (2048,)
        assert fp.dtype == np.uint8

    def test_deterministic(self) -> None:
        mol = parse_molecule("CC(=O)Oc1ccccc1C(=O)O")
        assert (compute_morgan_fingerprint(mol) == compute_morgan_fingerprint(mol)).all()

    def test_invariant_to_input_smiles_ordering(self) -> None:
        fp_a = compute_morgan_fingerprint(parse_molecule("CCO"))
        fp_b = compute_morgan_fingerprint(parse_molecule("OCC"))
        assert (fp_a == fp_b).all()

    def test_different_molecules_differ(self) -> None:
        fp_a = compute_morgan_fingerprint(parse_molecule("CCO"))
        fp_b = compute_morgan_fingerprint(parse_molecule("CC(=O)Oc1ccccc1C(=O)O"))
        assert not (fp_a == fp_b).all()

    def test_custom_radius_and_bits(self) -> None:
        fp = compute_morgan_fingerprint(parse_molecule("CCO"), radius=3, n_bits=512)
        assert fp.shape == (512,)

    def test_only_zeros_and_ones(self) -> None:
        fp = compute_morgan_fingerprint(parse_molecule("CC(=O)Oc1ccccc1C(=O)O"))
        assert set(np.unique(fp)).issubset({0, 1})


class TestChiralityAwareness:
    """RDKit's generator defaults includeChirality to False, which makes two
    stereoisomers of the same connectivity produce an identical fingerprint
    -- wrong for DrugSim, where identity.py already treats stereoisomers as
    distinct entities. Caught for real by a Phase 3 leakage check: 30
    train/test compound pairs were exact fingerprint duplicates purely
    because they were unflagged stereoisomer pairs under the achiral
    default."""

    def test_stereoisomers_get_different_fingerprints_by_default(self) -> None:
        r_alanine = compute_morgan_fingerprint(parse_molecule("C[C@H](N)C(=O)O"))
        s_alanine = compute_morgan_fingerprint(parse_molecule("C[C@@H](N)C(=O)O"))
        assert not (r_alanine == s_alanine).all()

    def test_include_chirality_false_collapses_stereoisomers(self) -> None:
        """The old (wrong-for-us) behaviour is still reachable explicitly,
        so a caller who genuinely wants connectivity-only matching can opt
        in -- but it is no longer the silent default."""
        r_alanine = compute_morgan_fingerprint(
            parse_molecule("C[C@H](N)C(=O)O"), include_chirality=False
        )
        s_alanine = compute_morgan_fingerprint(
            parse_molecule("C[C@@H](N)C(=O)O"), include_chirality=False
        )
        assert (r_alanine == s_alanine).all()

    def test_achiral_molecule_unaffected_by_chirality_flag(self) -> None:
        with_chirality = compute_morgan_fingerprint(parse_molecule("CCO"), include_chirality=True)
        without_chirality = compute_morgan_fingerprint(parse_molecule("CCO"), include_chirality=False)
        assert (with_chirality == without_chirality).all()
