"""Morgan (circular) fingerprints.

Python-side counterpart to the RDKit Postgres cartridge's ``morganbv_fp``
(``database/ddl/03_chemistry.sql``, ``compound.morgan_fp_r2_2048``) — same
radius and bit count, so a fingerprint computed here and one computed by the
cartridge from the same SMILES are the same fingerprint. Needed because model
training/inference computes features in Python, not SQL, and per TDS §6.6
training and serving must use the identical library — this module, not a
reimplementation elsewhere.
"""

from __future__ import annotations

import numpy as np
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

#: Matches compound.morgan_fp_r2_2048 (database/ddl/03_chemistry.sql):
#: radius 2 (~ECFP4), 2048 bits.
DEFAULT_RADIUS = 2
DEFAULT_N_BITS = 2048

__all__ = ["DEFAULT_N_BITS", "DEFAULT_RADIUS", "compute_morgan_fingerprint"]


def compute_morgan_fingerprint(
    mol: Chem.Mol,
    *,
    radius: int = DEFAULT_RADIUS,
    n_bits: int = DEFAULT_N_BITS,
    include_chirality: bool = True,
) -> np.ndarray:
    """Compute a folded Morgan fingerprint as a dense bit array.

    Args:
        mol: A sanitised molecule (see
            :func:`drugsim_chem.parsing.parse_molecule`). Should be the
            standardised structure, matching what descriptors are computed
            from, so a fingerprint and a descriptor vector for "the same
            compound" are always describing the identical structure.
        radius: Circular neighbourhood radius. Default 2 (ECFP4-equivalent).
        n_bits: Folded bit-vector length. Default 2048.
        include_chirality: Whether stereocentres affect the fingerprint.
            Defaults to ``True`` — RDKit's generator defaults this to
            ``False``, which makes two stereoisomers of the same
            connectivity produce an IDENTICAL fingerprint. That default is
            wrong for DrugSim: stereoisomers are treated as distinct
            entities everywhere else in this package (identity.py's
            ``inchikey_full`` is stereo-specific precisely because
            "stereoisomers can differ by orders of magnitude in potency and
              toxicity"), and a model trained on achiral fingerprints cannot
            distinguish inputs its own labels treat as different compounds
            — confirmed directly: a Phase 3 leakage check caught 30
            train/test compound pairs that were exact fingerprint
            duplicates purely because they were unflagged stereoisomer
            pairs under the achiral default.

    Returns:
        A ``(n_bits,)`` array of ``0``/``1`` values, dtype ``uint8``.

    Example:
        >>> from drugsim_chem.parsing import parse_molecule
        >>> fp = compute_morgan_fingerprint(parse_molecule("CCO"))
        >>> fp.shape
        (2048,)
    """
    generator = rdFingerprintGenerator.GetMorganGenerator(
        radius=radius, fpSize=n_bits, includeChirality=include_chirality
    )
    bit_vect = generator.GetFingerprint(mol)
    array = np.zeros((n_bits,), dtype=np.uint8)
    Chem.DataStructs.ConvertToNumpyArray(bit_vect, array)
    return array
