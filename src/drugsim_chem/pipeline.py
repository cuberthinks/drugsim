"""End-to-end compound processing: the single ETL entry point.

Ties parsing → standardisation → identity → descriptors → drug-likeness into
one function, so ETL code (and tests, and any future training/inference path)
calls one thing rather than five, in the right order, with the right data
flowing between stages. This is the concrete enforcement of "one chemistry
implementation" (TDS §6.6): there is exactly one place this sequence is
assembled.
"""

from __future__ import annotations

from dataclasses import dataclass

from rdkit import Chem

from drugsim_chem.descriptors import PhysicochemicalDescriptors, compute_descriptors
from drugsim_chem.drug_likeness import DrugLikenessAssessment, assess_drug_likeness
from drugsim_chem.identity import MolecularIdentity, compute_identity, stereo_completeness
from drugsim_chem.parsing import StructureFormat, parse_molecule
from drugsim_chem.standardize import (
    STANDARDIZATION_PIPELINE_VERSION,
    StandardizedStructure,
    standardize,
)

__all__ = ["ProcessedCompound", "process_structure"]


@dataclass(frozen=True)
class ProcessedCompound:
    """Everything computed for one input structure, ready for DB insertion.

    Attributes:
        source_smiles: The input, verbatim (P2/P3: raw form is preserved).
        standardization: Result of the standardisation stage.
        identity: Identity layers computed on the standardised structure —
            or, for a flagged mixture, on the cleaned-but-unstripped
            structure (there is no single parent to compute identity from).
        descriptors: Physicochemical descriptors, or ``None`` for a flagged
            mixture — descriptors on an unresolved multi-component structure
            would not describe a well-defined single compound.
        drug_likeness: Drug-likeness assessment, or ``None`` alongside
            ``descriptors`` for the same reason.
        stereo_completeness: One of the ``stereo_state_t`` values.
        is_mixture: Whether this structure was flagged as an unresolved
            mixture (Phase 1 Step 4 §2.2) — descriptors and drug-likeness are
            intentionally absent in that case rather than computed on an
            arbitrary component.
        standardized_smiles: SMILES of ``standardization.standardized_mol``
            (Phase 1 Step 4 §2.2) — the structure after cleanup and, where a
            single parent was identified, salt/solvate stripping. Always
            present, matching ``compound.standardized_smiles`` NOT NULL.
        parent_smiles: SMILES of ``standardization.parent_mol``, or ``None``
            when no single parent was identified (a genuine mixture, or a
            structure entirely composed of recognised salts) — matching
            ``compound.parent_smiles``, which is nullable for exactly that
            reason.
    """

    source_smiles: str
    standardization: StandardizedStructure
    identity: MolecularIdentity
    descriptors: PhysicochemicalDescriptors | None
    drug_likeness: DrugLikenessAssessment | None
    stereo_completeness: str
    is_mixture: bool
    standardized_smiles: str
    parent_smiles: str | None


def process_structure(
    structure: str,
    fmt: StructureFormat = "smiles",
    *,
    logd_74: float | None = None,
) -> ProcessedCompound:
    """Run the full compound-processing pipeline on one input structure.

    Args:
        structure: The input structure text.
        fmt: Input format.
        logd_74: Measured/predicted logD at pH 7.4, if available — passed
            through to drug-likeness for the Pfizer 3/75 flag.

    Returns:
        The processed compound. A flagged mixture has ``descriptors`` and
        ``drug_likeness`` as ``None`` — this is a deliberate, typed way of
        representing "not computed", never a zeroed-out or default value
        standing in for a real one.

    Raises:
        StructureError: If parsing, sanitisation, or standardisation fails.
            Per the "invalid molecules must be rejected or quarantined" rule,
            this exception is exactly the quarantine signal — a caller
            processing a batch should catch it per-record and route the
            failure to quarantine, never skip it silently and never let one
            bad record abort the batch.

    Example:
        >>> result = process_structure("CC(=O)Oc1ccccc1C(=O)O")
        >>> result.identity.inchikey_full
        'BSYNRYMUTXBXSQ-UHFFFAOYSA-N'
    """
    parsed = parse_molecule(structure, fmt)
    standardization = standardize(parsed)

    identity_source = standardization.standardized_mol
    identity = compute_identity(identity_source)
    stereo = stereo_completeness(identity_source)
    standardized_smiles = Chem.MolToSmiles(standardization.standardized_mol)
    parent_smiles = (
        Chem.MolToSmiles(standardization.parent_mol)
        if standardization.parent_mol is not None
        else None
    )

    if standardization.is_mixture:
        return ProcessedCompound(
            source_smiles=structure,
            standardization=standardization,
            identity=identity,
            descriptors=None,
            drug_likeness=None,
            stereo_completeness=stereo,
            is_mixture=True,
            standardized_smiles=standardized_smiles,
            parent_smiles=parent_smiles,
        )

    descriptors = compute_descriptors(
        standardization.standardized_mol, parent_mol=standardization.parent_mol
    )
    drug_likeness = assess_drug_likeness(
        standardization.standardized_mol, descriptors, logd_74=logd_74
    )

    return ProcessedCompound(
        source_smiles=structure,
        standardization=standardization,
        identity=identity,
        descriptors=descriptors,
        drug_likeness=drug_likeness,
        stereo_completeness=stereo,
        is_mixture=False,
        standardized_smiles=standardized_smiles,
        parent_smiles=parent_smiles,
    )
