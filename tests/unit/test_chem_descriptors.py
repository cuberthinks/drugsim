"""Tests for physicochemical descriptor computation.

Includes the corrected HBD/HBA convention mapping — verified against real
RDKit 2025.3.3, correcting a claim Phase 1 got wrong about which function pair
actually diverges (see descriptors.py module docstring for the full story).
"""

from __future__ import annotations

import pytest

from drugsim_chem.descriptors import compute_descriptors
from drugsim_chem.parsing import parse_molecule

pytestmark = pytest.mark.unit


class TestBasicDescriptors:
    """Verified against a live RDKit interpreter."""

    def test_ethanol_molecular_weight(self) -> None:
        d = compute_descriptors(parse_molecule("CCO"))
        assert round(d.mw_g_mol, 2) == 46.07

    def test_ethanol_formula_consistent_mass(self) -> None:
        d = compute_descriptors(parse_molecule("CCO"))
        assert abs(d.exact_mass_g_mol - d.mw_g_mol) < 0.5

    def test_aspirin_descriptors(self) -> None:
        d = compute_descriptors(parse_molecule("CC(=O)Oc1ccccc1C(=O)O"))
        assert round(d.mw_g_mol, 1) == 180.2
        assert d.aromatic_rings == 1
        assert d.ring_count == 1
        assert d.heavy_atom_count == 13
        assert d.formal_charge == 0
        assert round(d.tpsa_a2, 1) == 63.6

    def test_formal_charge_on_zwitterion(self) -> None:
        d = compute_descriptors(parse_molecule("[NH3+]CC(=O)[O-]"))
        assert d.formal_charge == 0  # zwitterion: net neutral despite local charges

    def test_largest_ring_size(self) -> None:
        d = compute_descriptors(parse_molecule("c1ccccc1"))
        assert d.largest_ring_size == 6

    def test_no_rings_gives_zero_largest_ring(self) -> None:
        d = compute_descriptors(parse_molecule("CCCC"))
        assert d.largest_ring_size == 0

    def test_fraction_csp3_all_sp3(self) -> None:
        d = compute_descriptors(parse_molecule("CCCC"))
        assert d.fraction_csp3 == 1.0

    def test_fraction_csp3_all_aromatic(self) -> None:
        d = compute_descriptors(parse_molecule("c1ccccc1"))
        assert d.fraction_csp3 == 0.0


class TestHbdHbaConventionsGenuinelyDiverge:
    """Pins the corrected mapping: *_lipinski uses the literal original
    Rule-of-Five convention, *_strict uses the chemically refined one — and
    they must actually produce different numbers for real molecules, or the
    distinction in the schema (two separate columns) would be pointless."""

    def test_aspirin_hba_conventions_diverge(self) -> None:
        """Verified interactively: aspirin's refined HBA=3, literal NOCount=4."""
        d = compute_descriptors(parse_molecule("CC(=O)Oc1ccccc1C(=O)O"))
        assert d.hba_strict == 3
        assert d.hba_lipinski == 4
        assert d.hba_lipinski != d.hba_strict

    def test_sulfonamide_conventions_diverge(self) -> None:
        d = compute_descriptors(parse_molecule("CS(=O)(=O)N"))
        assert (d.hbd_lipinski, d.hba_lipinski) != (d.hbd_strict, d.hba_strict)

    def test_guanidine_conventions_diverge_substantially(self) -> None:
        d = compute_descriptors(parse_molecule("NC(=N)N"))
        assert d.hbd_lipinski != d.hbd_strict

    def test_simple_alcohol_conventions_agree(self) -> None:
        """Not every molecule diverges — a simple, single-OH alcohol is
        unambiguous under both conventions. The point is that SOME molecules
        diverge, not that all do."""
        d = compute_descriptors(parse_molecule("CCO"))
        assert d.hbd_lipinski == d.hbd_strict == 1
        assert d.hba_lipinski == d.hba_strict == 1


class TestMwParent:
    """mw_parent_g_mol is only populated when a parent is explicitly supplied."""

    def test_none_when_no_parent_given(self) -> None:
        d = compute_descriptors(parse_molecule("CCO"))
        assert d.mw_parent_g_mol is None

    def test_populated_when_parent_given(self) -> None:
        salt = parse_molecule("CCN(CC)CC.Cl")
        parent = parse_molecule("CCN(CC)CC")
        d = compute_descriptors(salt, parent_mol=parent)
        assert d.mw_parent_g_mol is not None
        assert round(d.mw_parent_g_mol, 1) == round(101.19, 1)


class TestDeterminism:
    def test_repeated_computation_is_identical(self) -> None:
        mol_a = parse_molecule("CC(=O)Oc1ccccc1C(=O)O")
        mol_b = parse_molecule("CC(=O)Oc1ccccc1C(=O)O")
        assert compute_descriptors(mol_a) == compute_descriptors(mol_b)
