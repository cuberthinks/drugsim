"""Tests for molecular structure parsing.

Runs against REAL RDKit (pinned 2025.3.3) — this is genuine chemistry, not a
mock. The error-message capture mechanism (RDKit reroutes its C++ logger
through Python's sys.stderr rather than raising for many failure classes) was
verified interactively before this module was written; these tests pin that
behaviour so a future RDKit upgrade that changes it is caught.
"""

from __future__ import annotations

import pytest
from rdkit import Chem

from drugsim_core.errors import StructureError
from drugsim_chem.parsing import parse_molecule

pytestmark = pytest.mark.unit


class TestValidStructures:
    """The straightforward path, across formats."""

    def test_parses_simple_smiles(self) -> None:
        mol = parse_molecule("CCO")
        assert Chem.MolToSmiles(mol) == "CCO"

    def test_parses_aromatic_smiles(self) -> None:
        mol = parse_molecule("c1ccccc1")
        assert mol.GetNumAtoms() == 6

    def test_parses_smiles_with_stereochemistry(self) -> None:
        mol = parse_molecule("C[C@@H](N)C(=O)O")  # L-alanine
        assert mol.GetNumAtoms() == 6

    def test_parses_a_salt(self) -> None:
        """Multi-component structures parse fine at this stage — salt
        stripping is a later, distinct pipeline step (standardize.py)."""
        mol = parse_molecule("[Na+].[Cl-]")
        assert mol.GetNumAtoms() == 2

    def test_parses_molblock(self) -> None:
        ethanol_molblock = Chem.MolToMolBlock(Chem.MolFromSmiles("CCO"))
        mol = parse_molecule(ethanol_molblock, fmt="molblock")
        assert mol.GetNumAtoms() == 3  # includes explicit atoms only (no H by default)

    def test_parses_inchi(self) -> None:
        inchi = Chem.MolToInchi(Chem.MolFromSmiles("CCO"))
        mol = parse_molecule(inchi, fmt="inchi")
        assert Chem.MolToSmiles(mol) == "CCO"


class TestInvalidStructuresAreRejected:
    """Every failure mode must raise StructureError with a real diagnostic —
    never return None, never silently pass through a broken molecule."""

    def test_syntax_garbage_raises_with_real_message(self) -> None:
        with pytest.raises(StructureError) as exc_info:
            parse_molecule("not a smiles !!!")
        assert "detail" in exc_info.value.context
        assert exc_info.value.context["detail"]  # non-empty, real RDKit diagnostic

    def test_valence_error_raises_with_real_message(self) -> None:
        with pytest.raises(StructureError) as exc_info:
            parse_molecule("C(C)(C)(C)(C)C")  # 5-valent carbon
        assert "valence" in exc_info.value.context["detail"].lower()

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(StructureError, match="empty structure"):
            parse_molecule("")

    def test_whitespace_only_rejected(self) -> None:
        with pytest.raises(StructureError, match="empty structure"):
            parse_molecule("   ")

    def test_malformed_molblock_rejected(self) -> None:
        with pytest.raises(StructureError):
            parse_molecule("this is not a valid molblock", fmt="molblock")

    def test_malformed_inchi_rejected(self) -> None:
        with pytest.raises(StructureError):
            parse_molecule("not an inchi", fmt="inchi")

    def test_unsupported_format_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unsupported structure format"):
            parse_molecule("CCO", fmt="xyz")  # type: ignore[arg-type]

    def test_error_context_never_contains_raw_error_message_duplicated_in_message(self) -> None:
        """The exception's top-level message should be a stable, generic
        description; the structure-specific RDKit diagnostic belongs in
        context, not interpolated into the message string (drugsim_core.errors
        design: structured context passes through redaction; a formatted
        message may not)."""
        with pytest.raises(StructureError) as exc_info:
            parse_molecule("garbage!!!")
        assert exc_info.value.message == "could not parse smiles structure"


class TestNoConsoleNoise:
    """RDKit's raw C++ logger must not print duplicate diagnostics to the
    terminal — verified interactively; pinned here so a logging regression
    (e.g. from an RDKit upgrade resetting log sinks) is caught."""

    def test_parse_failure_does_not_print_to_real_stderr(self, capfd: pytest.CaptureFixture[str]) -> None:
        try:
            parse_molecule("not a smiles !!!")
        except StructureError:
            pass
        captured = capfd.readouterr()
        assert captured.err == ""


class TestDeterminism:
    """Parsing the same structure twice must yield an equivalent molecule —
    a baseline sanity check ahead of the standardisation idempotency tests."""

    def test_repeated_parse_yields_the_same_canonical_smiles(self) -> None:
        smiles_a = Chem.MolToSmiles(parse_molecule("c1ccccc1O"))
        smiles_b = Chem.MolToSmiles(parse_molecule("c1ccccc1O"))
        assert smiles_a == smiles_b
