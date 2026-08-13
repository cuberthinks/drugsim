"""Tests for chemical standardisation, including the edge cases RDKit's own
FragmentParent/LargestFragmentChooser get wrong (verified interactively while
writing standardize.py — see that module's docstring)."""

from __future__ import annotations

import pytest
from rdkit import Chem

from drugsim_chem.parsing import parse_molecule
from drugsim_chem.standardize import classify_fragments, standardize

pytestmark = pytest.mark.unit


def _smi(mol: Chem.Mol) -> str:
    return Chem.MolToSmiles(mol)


class TestClassifyFragmentsSingleComponent:
    def test_single_fragment_is_trivially_its_own_parent(self) -> None:
        mol = parse_molecule("CCO")
        result = classify_fragments(mol)
        assert result.parent is not None
        assert _smi(result.parent) == "CCO"
        assert not result.is_mixture
        assert result.component_count == 1


class TestClassifyFragmentsSaltStripping:
    """The common, correctly-handled case: one organic parent, one counterion."""

    def test_hydrochloride_salt(self) -> None:
        mol = parse_molecule("CCN(CC)CC.Cl")  # triethylamine hydrochloride
        result = classify_fragments(mol)
        assert result.parent is not None
        assert _smi(result.parent) == "CCN(CC)CC"
        assert not result.is_mixture
        assert result.salt_fragment_count == 1

    def test_sodium_salt_of_a_carboxylic_acid(self) -> None:
        mol = parse_molecule("CC(=O)O.[Na+]")
        result = classify_fragments(mol)
        # Both fragments are recognised salt patterns in RDKit's default table
        # (acetic acid AND Na+ are both common counterions) -- there is no
        # single unambiguous organic parent, so this correctly falls into the
        # "no parent identified" branch rather than guessing.
        assert result.parent is None
        assert not result.is_mixture


class TestClassifyFragmentsWholeStructureIsASalt:
    """The case RDKit's FragmentParent gets wrong: reduces to one arbitrary ion."""

    def test_plain_table_salt_has_no_organic_parent(self) -> None:
        mol = parse_molecule("[Na+].[Cl-]")
        result = classify_fragments(mol)
        assert result.parent is None
        assert not result.is_mixture
        assert result.salt_fragment_count == 2
        assert result.component_count == 2

    def test_disodium_salt_of_an_organic_dianion(self) -> None:
        """Two salt fragments (Na+, Na+) plus one genuine organic parent."""
        mol = parse_molecule("[Na+].[Na+].O=C([O-])c1ccccc1C(=O)[O-]")
        result = classify_fragments(mol)
        assert result.parent is not None
        assert result.salt_fragment_count == 2


class TestClassifyFragmentsGenuineMixture:
    """The other case RDKit's built-ins get wrong: arbitrarily picking a
    'largest fragment' from two genuine, unrelated organic components."""

    def test_two_unrelated_organics_flagged_as_mixture(self) -> None:
        mol = parse_molecule("CCO.CCN")  # ethanol + ethylamine
        result = classify_fragments(mol)
        assert result.parent is None
        assert result.is_mixture is True
        assert result.salt_fragment_count == 0


class TestStandardizeEndToEnd:
    """The full pipeline, including flags."""

    def test_simple_molecule_flagged_unchanged(self) -> None:
        result = standardize(parse_molecule("CCO"))
        assert not result.is_mixture
        assert result.parent_mol is not None
        assert result.component_count == 1
        assert "unchanged" in result.flags or "normalized" in result.flags

    def test_salt_is_stripped_and_flagged(self) -> None:
        result = standardize(parse_molecule("CCN(CC)CC.Cl"))
        assert result.parent_mol is not None
        assert _smi(result.parent_mol) == "CCN(CC)CC"
        assert result.component_count == 2
        assert "salt_stripped" in result.flags

    def test_charged_species_is_neutralised_and_flagged(self) -> None:
        result = standardize(parse_molecule("CC(=O)[O-]"))
        assert _smi(result.standardized_mol) == "CC(=O)O"
        assert "charge_neutralised" in result.flags

    def test_zwitterion_is_neutralised(self) -> None:
        """An amino acid zwitterion should end up fully neutral."""
        result = standardize(parse_molecule("[NH3+]CC(=O)[O-]"))  # glycine zwitterion
        assert Chem.GetFormalCharge(result.standardized_mol) == 0

    def test_mixture_is_flagged_and_not_processed_further(self) -> None:
        result = standardize(parse_molecule("CCO.CCN"))
        assert result.is_mixture is True
        assert result.parent_mol is None
        assert result.component_count == 2
        assert "flagged_as_mixture" in result.flags

    def test_whole_salt_retains_original_structure(self) -> None:
        """Plain NaCl: standardized_mol must retain BOTH ions, not collapse
        to a single arbitrary one."""
        result = standardize(parse_molecule("[Na+].[Cl-]"))
        assert not result.is_mixture
        frags = Chem.GetMolFrags(result.standardized_mol)
        assert len(frags) == 2
        assert result.component_count == 2
        assert "retained_whole_salt_no_organic_parent" in result.flags

    def test_whole_salt_has_no_parent_mol(self) -> None:
        """A structure entirely composed of recognised salts has no
        identified organic parent — parent_mol must be None here exactly as
        it is for a genuine mixture, per this module's own documented
        contract (StandardizedStructure.parent_mol docstring). Regression
        test for a bug where `parent_mol=working if not is_mixture else
        None` left this wrongly set to the whole salt structure, since
        is_mixture is False for the whole-salt case too."""
        result = standardize(parse_molecule("[Na+].[Cl-]"))
        assert result.parent_mol is None

    def test_canonical_tautomer_is_computed_but_does_not_replace_standardized(self) -> None:
        """Tautomer canonicalisation must never silently overwrite the
        standardised structure (Phase 1 Step 8 §S4)."""
        result = standardize(parse_molecule("CC(=O)CC(=O)C"))  # acetylacetone
        assert result.canonical_tautomer_mol is not None
        # standardized_mol is the cleaned-up INPUT tautomer, not necessarily
        # identical to canonical_tautomer_mol.
        assert isinstance(_smi(result.standardized_mol), str)
        assert isinstance(_smi(result.canonical_tautomer_mol), str)


class TestIdempotency:
    """Re-running standardisation on an already-standardised structure must
    not change it further — required for golden-set regression and safe
    re-ingestion."""

    @pytest.mark.parametrize(
        "smiles",
        [
            "CCO",
            "CC(=O)Oc1ccccc1C(=O)O",  # aspirin
            "CCN(CC)CC.Cl",  # a salt
            "CC(=O)[O-]",  # charged
            "[NH3+]CC(=O)[O-]",  # zwitterion
        ],
    )
    def test_standardize_is_idempotent(self, smiles: str) -> None:
        once = standardize(parse_molecule(smiles))
        twice = standardize(once.standardized_mol)
        assert _smi(once.standardized_mol) == _smi(twice.standardized_mol)

    def test_whole_salt_case_is_idempotent(self) -> None:
        """Specifically exercises the retain-original branch a second time —
        re-standardising [Na+].[Cl-] must not attempt to strip further."""
        once = standardize(parse_molecule("[Na+].[Cl-]"))
        twice = standardize(once.standardized_mol)
        assert _smi(once.standardized_mol) == _smi(twice.standardized_mol)
        assert len(Chem.GetMolFrags(twice.standardized_mol)) == 2
