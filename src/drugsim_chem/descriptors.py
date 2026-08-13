"""Physicochemical descriptor computation.

Matches the column set in ``database/ddl/03_chemistry.sql`` exactly. Every
value is a deterministic function of structure, computed under a pinned
toolchain (:mod:`drugsim_core.version`) — this is why descriptors live in a
table keyed by ``(compound_uid, descriptor_spec_version)`` rather than as
columns on ``compound`` (ADR-005).

**Correction to Phase 1's documented HBD/HBA claim**, found while writing this
module: Phase 1 named ``Lipinski.NumHDonors`` vs ``rdMolDescriptors.CalcNumHBD``
as RDKit's two divergent HBD conventions. Verified directly against the
installed RDKit 2025.3.3 source: they are not divergent — ``Lipinski.NumHDonors``
is a **direct alias** for ``rdMolDescriptors.CalcNumHBD`` (``NumHDonors = lambda
x: rdMolDescriptors.CalcNumHBD(x)`` in ``rdkit/Chem/Lipinski.py``). The
functions that actually implement the ORIGINAL, literally-published Lipinski
Rule of Five convention (donors = count of N-H + O-H bonds; acceptors = count
of all N + O atoms) are ``Lipinski.NHOHCount`` / ``Lipinski.NOCount`` — confusingly
named, since they live in the same module as the refined functions but are not
what a reader would guess from "NumHDonors" being present nearby. Verified with
a battery of molecules (sulfonamide, aspirin, pyrrole, aniline, guanidine) that
these two conventions genuinely do diverge — aspirin: refined HBA=3, literal
Lipinski NOCount=4.

``hbd_lipinski``/``hba_lipinski`` below therefore map to ``NHOHCount``/``NOCount``
(the convention the original Rule of Five was calibrated against), and
``hbd_strict``/``hba_strict`` map to ``CalcNumHBD``/``CalcNumHBA`` (the
chemically refined convention, useful for other modelling but NOT what Lipinski
violations should be evaluated against).
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem
from rdkit.Chem import Crippen, Descriptors, Lipinski, rdMolDescriptors

__all__ = ["DESCRIPTOR_SPEC_VERSION", "PhysicochemicalDescriptors", "compute_descriptors"]

#: Bump when the descriptor set or any computation convention changes.
DESCRIPTOR_SPEC_VERSION = "v1"


@dataclass(frozen=True)
class PhysicochemicalDescriptors:
    """One row's worth of ``compound_descriptor`` values.

    Field names and units match ``database/ddl/03_chemistry.sql`` exactly —
    see that file for the CHECK constraints each value must satisfy.
    """

    mw_g_mol: float
    exact_mass_g_mol: float
    logp_crippen: float
    molar_refractivity: float
    tpsa_a2: float
    rotatable_bonds: int
    aromatic_rings: int
    ring_count: int
    heavy_atom_count: int
    formal_charge: int
    hbd_lipinski: int
    hba_lipinski: int
    hbd_strict: int
    hba_strict: int
    heteroatom_count: int
    fraction_csp3: float
    num_stereocentres: int
    largest_ring_size: int
    mw_parent_g_mol: float | None = None


def compute_descriptors(
    mol: Chem.Mol,
    *,
    parent_mol: Chem.Mol | None = None,
) -> PhysicochemicalDescriptors:
    """Compute the full physicochemical descriptor set for a molecule.

    Args:
        mol: A sanitised, standardised molecule (see
            :func:`drugsim_chem.standardize.standardize`). Descriptors should
            be computed on the standardised structure, not the raw parse, so
            that e.g. a compound and its differently-drawn tautomer converge
            on the same values.
        parent_mol: If the compound is a salt, the desalted parent — used only
            to populate ``mw_parent_g_mol``. ``None`` when there is no
            distinct parent (single-component structures, or structures where
            no organic parent was identified).

    Returns:
        The computed descriptors.

    Example:
        >>> from drugsim_chem.parsing import parse_molecule
        >>> d = compute_descriptors(parse_molecule("CCO"))
        >>> round(d.mw_g_mol, 2)
        46.07
    """
    ring_info = mol.GetRingInfo()
    largest_ring = max((len(ring) for ring in ring_info.AtomRings()), default=0)

    stereocentres = Chem.FindMolChiralCenters(
        mol, includeUnassigned=True, useLegacyImplementation=False
    )

    return PhysicochemicalDescriptors(
        mw_g_mol=Descriptors.MolWt(mol),
        exact_mass_g_mol=Descriptors.ExactMolWt(mol),
        logp_crippen=Crippen.MolLogP(mol),
        molar_refractivity=Crippen.MolMR(mol),
        tpsa_a2=Descriptors.TPSA(mol),
        rotatable_bonds=Lipinski.NumRotatableBonds(mol),
        aromatic_rings=rdMolDescriptors.CalcNumAromaticRings(mol),
        ring_count=rdMolDescriptors.CalcNumRings(mol),
        heavy_atom_count=Descriptors.HeavyAtomCount(mol),
        formal_charge=Chem.GetFormalCharge(mol),
        # See module docstring: *_lipinski uses the literal original Rule-of-
        # Five convention (NHOHCount/NOCount), NOT Lipinski.NumHDonors, which
        # is an alias for the refined convention despite its module name.
        hbd_lipinski=Lipinski.NHOHCount(mol),
        hba_lipinski=Lipinski.NOCount(mol),
        hbd_strict=rdMolDescriptors.CalcNumHBD(mol),
        hba_strict=rdMolDescriptors.CalcNumHBA(mol),
        heteroatom_count=Lipinski.NumHeteroatoms(mol),
        fraction_csp3=rdMolDescriptors.CalcFractionCSP3(mol),
        num_stereocentres=len(stereocentres),
        largest_ring_size=largest_ring,
        mw_parent_g_mol=Descriptors.MolWt(parent_mol) if parent_mol is not None else None,
    )
