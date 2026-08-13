"""Chemical identity: InChI, InChIKey, canonical/isomeric SMILES, scaffolds.

Implements the four-layer identity model from Phase 1 Step 2 §5. A single
identifier cannot serve deduplication, stereochemistry, and split-assignment
leakage prevention simultaneously — each layer below exists for a distinct,
named purpose, and callers must pick the right one deliberately rather than
reaching for whichever is convenient.
"""

from __future__ import annotations

import contextlib
import io
import re
from dataclasses import dataclass, field

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors
from rdkit.Chem.Scaffolds import MurckoScaffold

from drugsim_core.errors import StructureError

#: RDKit prepends a wall-clock "[HH:MM:SS] " timestamp to logged messages.
#: Stripped from captured warnings so they are deterministic (P1) — verified
#: necessary by the golden-set regression test, which failed on this exact
#: field differing between fixture generation and test run time.
_TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d{2}:\d{2}:\d{2}\]\s*")

#: RDKit's CalcMolFormula appends a charge suffix (bare "+"/"-" for magnitude
#: 1, sign-then-digit e.g. "-4" for larger magnitudes — verified directly;
#: the digit-then-sign order this module originally assumed was WRONG and
#: silently truncated element counts, e.g. "C2H3O2-" -> "C2H3O" instead of
#: "C2H3O2"). "+"/"-" never otherwise appear in a Hill formula, so stripping
#: a trailing [+-] followed by optional digits is unambiguous. Charge is
#: already captured separately in compound_descriptor.formal_charge, so
#: molecular_formula represents elemental composition only, matching the
#: database's molecular_formula CHECK constraint (03_chemistry.sql).
_FORMULA_CHARGE_SUFFIX_RE = re.compile(r"[+-][0-9]*$")

__all__ = ["MolecularIdentity", "compute_identity"]


@dataclass(frozen=True)
class MolecularIdentity:
    """The four identity layers plus the scaffold, for one structure.

    Attributes:
        canonical_smiles: RDKit canonical SMILES, stereochemistry stripped.
            Used for deduplication of connectivity regardless of stereo.
        isomeric_smiles: RDKit canonical SMILES, stereochemistry retained.
            The structure as actually specified.
        inchi: Standard InChI.
        inchikey_full: 27-character InChIKey — exact identity, stereo- and
            isotope-specific. The layer for deduplication of identical
            entities (``uq_compound_inchikey``).
        inchikey_skeleton: First 14 characters of ``inchikey_full` —
            connectivity only, stereochemistry-blind. Used **only** for split
            assignment and stereoisomer grouping (ADR-009) — never as a merge
            key, since two stereoisomers can differ by orders of magnitude in
            potency and toxicity.
        bemis_murcko_scaffold: The Bemis-Murcko scaffold SMILES, or ``None``
            for an acyclic structure (a scaffold requires at least one ring).
        num_stereocentres: Count of potential stereocentres, assigned or not —
            drives ``stereo_completeness`` classification upstream.
        num_defined_stereocentres: Count with an assigned configuration.
        inchi_warnings: Diagnostics RDKit's InChI generator emitted, if any —
            e.g. ``"WARNING: Proton(s) added/removed"`` for salts and some
            zwitterions/tautomers, where InChI's normalisation algorithm does
            not exactly preserve the input's formal charges. Captured rather
            than discarded (found via ``rdBase.LogToPythonStderr`` +
            ``redirect_stderr`` while writing this module): for a genuine
            structural ambiguity in a real compound this can be informative
            QA signal, not merely chatter, so it is surfaced on the record
            rather than silently suppressed the way standardize.py's
            ``BlockLogs()`` legitimately discards pure progress noise.
        molecular_formula: Hill-notation elemental formula (e.g. ``C9H8O4``),
            charge suffix stripped — charge is tracked separately as
            ``compound_descriptor.formal_charge``, so this column represents
            elemental composition only, matching ``compound.molecular_formula``'s
            CHECK constraint.
    """

    canonical_smiles: str
    isomeric_smiles: str
    inchi: str
    inchikey_full: str
    inchikey_skeleton: str
    bemis_murcko_scaffold: str | None
    num_stereocentres: int
    num_defined_stereocentres: int
    molecular_formula: str
    inchi_warnings: tuple[str, ...] = field(default_factory=tuple)


def compute_identity(mol: Chem.Mol) -> MolecularIdentity:
    """Compute all identity layers for an already-parsed, sanitised molecule.

    Args:
        mol: A sanitised RDKit ``Mol`` (see
            :func:`drugsim_chem.parsing.parse_molecule`).

    Returns:
        The computed identity.

    Raises:
        StructureError: If InChI generation fails. RDKit's InChI generator
            rejects some valid-for-SMILES structures it cannot represent
            (certain organometallics, some polymeric/undefined structures) —
            this is a real, separate failure mode from parsing, verified
            directly rather than assumed, and reported the same way parsing
            failures are.

    Example:
        >>> from drugsim_chem.parsing import parse_molecule
        >>> identity = compute_identity(parse_molecule("CCO"))
        >>> identity.inchikey_full
        'LFQSCWFLJHTTHZ-UHFFFAOYSA-N'
    """
    canonical_smiles = Chem.MolToSmiles(mol, isomericSmiles=False)
    isomeric_smiles = Chem.MolToSmiles(mol, isomericSmiles=True)

    # RDKit's InChI generator can print diagnostics (e.g. "WARNING: Proton(s)
    # added/removed" for salts/zwitterions) via the same rerouted-to-stderr
    # mechanism configured in drugsim_chem/__init__.py — captured here rather
    # than left to print, and surfaced on the record rather than discarded.
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        inchi = Chem.MolToInchi(mol)
    # The wall-clock "[HH:MM:SS]" prefix RDKit prepends is stripped: a
    # deterministic function's output must not depend on what time it happened
    # to run (P1). Caught by the golden-set regression test comparing the
    # same molecule processed at fixture-generation time vs. test-run time —
    # the raw, timestamped text differed on every run despite being the exact
    # same warning for the exact same molecule.
    inchi_warnings = tuple(
        _TIMESTAMP_PREFIX_RE.sub("", line).strip()
        for line in buffer.getvalue().splitlines()
        if line.strip()
    )

    if not inchi:
        msg = "InChI generation failed"
        raise StructureError(msg, detail="RDKit MolToInchi returned an empty string")

    inchikey_full = Chem.InchiToInchiKey(inchi)
    if not inchikey_full:
        msg = "InChIKey generation failed"
        raise StructureError(msg, detail="RDKit InchiToInchiKey returned an empty string")

    scaffold_smiles = _bemis_murcko_scaffold(mol)

    stereocentres = Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False
    )
    defined = sum(1 for _, label in stereocentres if label != "?")

    # CalcMolFormula appends a charge suffix for ionic species (verified
    # directly: sign character first, then optional magnitude digits, e.g.
    # "C2H3O2-", "C10H2O8-4") which is stripped here — see
    # _FORMULA_CHARGE_SUFFIX_RE above for why.
    molecular_formula = _FORMULA_CHARGE_SUFFIX_RE.sub("", rdMolDescriptors.CalcMolFormula(mol))

    return MolecularIdentity(
        canonical_smiles=canonical_smiles,
        isomeric_smiles=isomeric_smiles,
        inchi=inchi,
        inchikey_full=inchikey_full,
        inchikey_skeleton=inchikey_full[:14],
        bemis_murcko_scaffold=scaffold_smiles,
        num_stereocentres=len(stereocentres),
        num_defined_stereocentres=defined,
        molecular_formula=molecular_formula,
        inchi_warnings=inchi_warnings,
    )


def _bemis_murcko_scaffold(mol: Chem.Mol) -> str | None:
    """Compute the Bemis-Murcko scaffold, or None for an acyclic molecule.

    Args:
        mol: A sanitised molecule.

    Returns:
        Scaffold SMILES, or ``None`` if the molecule has no rings (a scaffold
        is undefined for a purely acyclic structure — verified directly:
        RDKit's ``GetScaffoldForMol`` returns a valid but ring-less,
        semantically meaningless "scaffold" for e.g. plain alkanes, which
        this function normalises to ``None`` instead).
    """
    if mol.GetRingInfo().NumRings() == 0:
        return None
    scaffold = MurckoScaffold.GetScaffoldForMol(mol)
    if scaffold is None or scaffold.GetNumAtoms() == 0:
        return None
    return Chem.MolToSmiles(scaffold)


def stereo_completeness(mol: Chem.Mol) -> str:
    """Classify a molecule's stereochemical completeness.

    Args:
        mol: A sanitised molecule.

    Returns:
        One of ``fully_defined``, ``partially_defined``, ``undefined``, or
        ``not_applicable`` (no stereocentres present at all) — matching the
        ``stereo_state_t`` enum (Phase 1 Step 3 §2).
    """
    stereocentres = Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False
    )
    if not stereocentres:
        return "not_applicable"

    defined = sum(1 for _, label in stereocentres if label != "?")
    if defined == 0:
        return "undefined"
    if defined == len(stereocentres):
        return "fully_defined"
    return "partially_defined"
