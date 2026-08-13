"""Molecular structure parsing and sanitisation.

RDKit's default behaviour is to return ``None`` on both syntax and
sanitisation failures, printing the real diagnostic to its own C++ logger
rather than raising a catchable Python exception — verified directly against
the installed RDKit 2025.3.3 while writing this module, not assumed from
documentation. Getting the actual message (rather than a bare "invalid input")
matters because TDS §5.3 depends on it: a chemist can act on "explicit valence
for atom # 0 C, 5, is greater than permitted" but not on "parse failed".

The fix is a two-stage parse — structure first with ``sanitize=False`` (which
only fails on genuine syntax errors), then an explicit
:func:`~rdkit.Chem.SanitizeMol` call, which *does* raise a real exception —
combined with rerouting RDKit's logger through Python's ``sys.stderr`` so a
syntax-stage failure's message is capturable too.
"""

from __future__ import annotations

import contextlib
import io
from typing import Literal

from rdkit import Chem

from drugsim_core.errors import StructureError

__all__ = ["StructureFormat", "parse_molecule"]

StructureFormat = Literal["smiles", "molblock", "inchi"]

# RDKit's C++ logger is rerouted through Python's sys.stderr, with the direct-
# to-terminal error/warning/info sinks disabled, in drugsim_chem/__init__.py
# — not here. Python guarantees the package __init__ runs before this module
# does, so the configuration is already in effect by the time parse_molecule
# is called; duplicating the rdBase calls here would just reconfigure the same
# global state a second time for no benefit.


def parse_molecule(structure: str, fmt: StructureFormat = "smiles") -> Chem.Mol:
    """Parse and sanitise a molecular structure.

    Args:
        structure: The structure text.
        fmt: Input format.

    Returns:
        A sanitised RDKit ``Mol``. Guaranteed non-empty (at least one atom) —
        an empty structure is rejected here even though RDKit itself
        considers a zero-atom molecule trivially "valid" (verified directly:
        ``Chem.MolFromSmiles("")`` both parses and sanitises without error).
        A record with zero atoms is not a compound.

    Raises:
        StructureError: If the structure cannot be parsed or sanitised, or is
            empty. Carries the real RDKit diagnostic as ``context["detail"]``
            and never contains the raw structure text in the exception
            message itself — only in ``context``, which passes through the
            redaction pipeline (``drugsim_core.redaction``) before it can
            reach a log.
        ValueError: If ``fmt`` is not a supported format.

    Example:
        >>> mol = parse_molecule("CCO")
        >>> Chem.MolToSmiles(mol)
        'CCO'
    """
    if not structure or not structure.strip():
        msg = "empty structure"
        raise StructureError(msg, fmt=fmt)

    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        mol = _parse_unsanitized(structure, fmt)

        if mol is None:
            detail = buffer.getvalue().strip() or "parser returned no result"
            msg = f"could not parse {fmt} structure"
            raise StructureError(msg, fmt=fmt, detail=detail)

        try:
            Chem.SanitizeMol(mol)
        except Exception as exc:  # RDKit raises several distinct exception types here
            msg = f"could not sanitise {fmt} structure"
            raise StructureError(msg, fmt=fmt, detail=str(exc)) from exc

    if mol.GetNumAtoms() == 0:
        msg = f"{fmt} structure parsed to zero atoms"
        raise StructureError(msg, fmt=fmt)

    return mol


def _parse_unsanitized(structure: str, fmt: StructureFormat) -> Chem.Mol | None:
    """Parse without sanitising, so syntax and sanitisation failures are distinguishable.

    Args:
        structure: The structure text.
        fmt: Input format.

    Returns:
        An unsanitised ``Mol``, or ``None`` if parsing itself failed.

    Raises:
        ValueError: If ``fmt`` is unsupported.
    """
    if fmt == "smiles":
        return Chem.MolFromSmiles(structure, sanitize=False)
    if fmt == "molblock":
        return Chem.MolFromMolBlock(structure, sanitize=False)
    if fmt == "inchi":
        # InChI round-trips through RDKit's own sanitisation internally; a
        # second explicit SanitizeMol call in parse_molecule is a harmless
        # no-op on an already-valid structure and keeps this function's
        # contract uniform across formats.
        return Chem.MolFromInchi(structure, sanitize=True)
    msg = f"unsupported structure format: {fmt!r}"
    raise ValueError(msg)
