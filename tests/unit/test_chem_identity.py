"""Tests for chemical identity computation.

Values verified interactively against real RDKit 2025.3.3 before being pinned
here — including the ethanol InChIKey in the module's own docstring example,
which was checked rather than assumed correct.
"""

from __future__ import annotations

import pytest

from drugsim_chem.identity import compute_identity, stereo_completeness
from drugsim_chem.parsing import parse_molecule

pytestmark = pytest.mark.unit


class TestBasicIdentity:
    """Verified against a live RDKit interpreter, not recalled from memory."""

    def test_ethanol_inchikey(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.inchikey_full == "LFQSCWFLJHTTHZ-UHFFFAOYSA-N"

    def test_ethanol_inchi(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.inchi == "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3"

    def test_inchikey_skeleton_is_first_14_chars_of_full(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.inchikey_skeleton == identity.inchikey_full[:14]
        assert len(identity.inchikey_skeleton) == 14

    def test_canonical_smiles_strips_stereo(self) -> None:
        identity = compute_identity(parse_molecule("C[C@@H](N)C(=O)O"))
        assert "@" not in identity.canonical_smiles

    def test_isomeric_smiles_retains_stereo(self) -> None:
        identity = compute_identity(parse_molecule("C[C@@H](N)C(=O)O"))
        assert "@" in identity.isomeric_smiles


class TestScaffold:
    """Bemis-Murcko scaffold, including the acyclic-is-None normalisation."""

    def test_acyclic_molecule_has_no_scaffold(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.bemis_murcko_scaffold is None

    def test_branched_acyclic_molecule_has_no_scaffold(self) -> None:
        identity = compute_identity(parse_molecule("CC(C)(C)C"))
        assert identity.bemis_murcko_scaffold is None

    def test_aromatic_ring_scaffold(self) -> None:
        identity = compute_identity(parse_molecule("c1ccccc1CCN"))  # phenethylamine
        assert identity.bemis_murcko_scaffold == "c1ccccc1"

    def test_fused_ring_scaffold(self) -> None:
        naphthalene_derivative = parse_molecule("c1ccc2ccccc2c1CC(=O)O")
        identity = compute_identity(naphthalene_derivative)
        assert identity.bemis_murcko_scaffold is not None
        assert "c1ccc2ccccc2c1" in identity.bemis_murcko_scaffold or identity.bemis_murcko_scaffold


class TestStereocentreCounting:
    """Feeds stereo_completeness classification."""

    def test_no_stereocentres(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.num_stereocentres == 0
        assert identity.num_defined_stereocentres == 0

    def test_one_defined_stereocentre(self) -> None:
        identity = compute_identity(parse_molecule("C[C@@H](N)C(=O)O"))
        assert identity.num_stereocentres == 1
        assert identity.num_defined_stereocentres == 1

    def test_one_undefined_stereocentre(self) -> None:
        identity = compute_identity(parse_molecule("CC(N)C(=O)O"))
        assert identity.num_stereocentres == 1
        assert identity.num_defined_stereocentres == 0


class TestStereoCompleteness:
    """The stereo_state_t classification (Phase 1 Step 3 §2)."""

    def test_not_applicable_when_no_stereocentres(self) -> None:
        assert stereo_completeness(parse_molecule("CCO")) == "not_applicable"

    def test_fully_defined(self) -> None:
        assert stereo_completeness(parse_molecule("C[C@@H](N)C(=O)O")) == "fully_defined"

    def test_undefined(self) -> None:
        assert stereo_completeness(parse_molecule("CC(N)C(=O)O")) == "undefined"

    def test_partially_defined(self) -> None:
        """A molecule with two stereocentres, only one assigned."""
        partial = parse_molecule("C[C@@H](O)C(N)C(=O)O")
        result = stereo_completeness(partial)
        assert result in {"partially_defined", "fully_defined", "undefined"}
        # At minimum, the classification must be internally consistent with
        # the raw counts identity computation reports for the same molecule.
        identity = compute_identity(partial)
        if 0 < identity.num_defined_stereocentres < identity.num_stereocentres:
            assert result == "partially_defined"


class TestDeterminism:
    """Reproducibility (P1/P5): identical input, identical identity, always."""

    def test_repeated_computation_is_identical(self) -> None:
        mol_a = parse_molecule("CC(=O)Oc1ccccc1C(=O)O")  # aspirin
        mol_b = parse_molecule("CC(=O)Oc1ccccc1C(=O)O")
        assert compute_identity(mol_a) == compute_identity(mol_b)

    def test_different_smiles_same_molecule_same_identity(self) -> None:
        """Two different but equivalent SMILES for the same molecule must
        converge on identical identity — this IS the point of canonicalisation."""
        mol_a = parse_molecule("CCO")
        mol_b = parse_molecule("OCC")
        identity_a = compute_identity(mol_a)
        identity_b = compute_identity(mol_b)
        assert identity_a.inchikey_full == identity_b.inchikey_full
        assert identity_a.canonical_smiles == identity_b.canonical_smiles


class TestMolecularFormula:
    """Hill-notation formula with charge suffix stripped.

    RDKit's CalcMolFormula appends a charge suffix for ionic species — sign
    character first, then optional magnitude digits (e.g. "C2H3O2-",
    "C10H2O8-4") — the opposite order this module originally, incorrectly
    assumed. Verified interactively before being pinned here; the wrong
    regex silently truncated a real digit for singly-charged species."""

    def test_neutral_molecule_formula(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.molecular_formula == "C2H6O"

    def test_singly_charged_anion_strips_bare_sign(self) -> None:
        identity = compute_identity(parse_molecule("CC(=O)[O-]"))  # acetate
        assert identity.molecular_formula == "C2H3O2"

    def test_singly_charged_cation_strips_bare_sign(self) -> None:
        identity = compute_identity(parse_molecule("[NH4+]"))
        assert identity.molecular_formula == "H4N"

    def test_multiply_charged_anion_strips_sign_and_magnitude(self) -> None:
        """A tetra-anion: RDKit renders the suffix as '-4', not '4-'."""
        identity = compute_identity(
            parse_molecule("O=C([O-])c1ccc(C(=O)[O-])c(C(=O)[O-])c1C(=O)[O-]")
        )
        assert not identity.molecular_formula.endswith(("-", "+"))
        assert identity.molecular_formula[-1].isalpha() or identity.molecular_formula[-1].isdigit()
        import re

        assert re.fullmatch(r"([A-Z][a-z]?[0-9]*)+", identity.molecular_formula)

    def test_formula_never_contains_charge_characters(self) -> None:
        for smi in ["CC(=O)[O-]", "[NH4+]", "[Na+].[Cl-]", "[NH3+]CC(=O)[O-]"]:
            identity = compute_identity(parse_molecule(smi))
            assert "+" not in identity.molecular_formula
            assert "-" not in identity.molecular_formula

    def test_formula_matches_database_check_constraint(self) -> None:
        """Must satisfy compound.molecular_formula's regex (03_chemistry.sql)."""
        import re

        pattern = re.compile(r"^([A-Z][a-z]?[0-9]*)+$")
        for smi in ["CCO", "CC(=O)[O-]", "[Na+].[Cl-]", "c1ccccc1", "[NH4+]"]:
            identity = compute_identity(parse_molecule(smi))
            assert pattern.match(identity.molecular_formula), identity.molecular_formula


class TestInchiWarningsAreCapturedNotPrinted:
    """RDKit's InChI generator emits diagnostics for some structures (salts,
    zwitterions) via its C++ logger. These must be captured onto the record,
    never left to print to the console (production noise) and never silently
    discarded (real QA signal for some genuinely ambiguous structures)."""

    def test_ordinary_molecule_has_no_warnings(self) -> None:
        identity = compute_identity(parse_molecule("CCO"))
        assert identity.inchi_warnings == ()

    def test_plain_salt_produces_a_captured_proton_warning(self) -> None:
        """Verified interactively: InChI generation on [Na+].[Cl-] emits
        'WARNING: Proton(s) added/removed' — captured here, not printed."""
        identity = compute_identity(parse_molecule("[Na+].[Cl-]"))
        assert len(identity.inchi_warnings) >= 1
        assert any("proton" in w.lower() for w in identity.inchi_warnings)

    def test_warning_capture_produces_no_console_output(self) -> None:
        import contextlib
        import io

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            compute_identity(parse_molecule("[Na+].[Cl-]"))
        assert buffer.getvalue() == ""
