"""The shared curation orchestration: raw rows in, ledger + curated compounds out.

This is the one place the sequence "standardise each distinct molecule once
-> build a ledger row per raw measurement -> tag exact duplicates -> group
by compound -> aggregate -> patch conflict_status back onto the
contributing ledger rows" is assembled — the same discipline
``drugsim_chem.pipeline.process_structure`` already applies to the
chemistry sequence. Both live driver scripts
(``models/admet/{herg,cyp3a4}_inhibition/curate_measurements.py``) and the
golden-fixture generator/test
(``scripts/generate_curation_golden_fixtures.py`` /
``tests/golden/test_curation_golden_regression.py``) call this function
rather than each re-implementing the sequence — three independent copies of
this logic would drift the same way any un-shared code does.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import Any, Optional

from drugsim_chem import process_structure
from drugsim_core.errors import StructureError

from drugsim_curation.assay_context import AssayMetadata
from drugsim_curation.curated_view import CuratedCompoundRow, build_curated_compound
from drugsim_curation.ledger import MeasurementLedgerRow, build_ledger_row, find_exact_duplicate_measurements
from drugsim_curation.provenance import LicenseResolution
from drugsim_curation.units import resolve_unit

__all__ = ["CurationRunResult", "curate_raw_rows"]


@dataclasses.dataclass(frozen=True)
class CurationRunResult:
    """The two outputs of one curation run, sorted for deterministic output.

    Attributes:
        ledger_rows: One per raw row, ``conflict_status`` already patched.
        curated_compounds: One per resolved (valid-structure) compound.
    """

    ledger_rows: list[MeasurementLedgerRow]
    curated_compounds: list[CuratedCompoundRow]


def curate_raw_rows(
    raw_rows: list[dict[str, Any]],
    *,
    source_dataset_id: str,
    endpoint: str,
    license_resolution: LicenseResolution,
    bad_validity_flags: frozenset[str],
    assay_metadata_by_id: dict[str, AssayMetadata],
    blocker_threshold_nm: float,
    dataset_version: str,
    retrieved_at: str,
    curated_at: str,
    progress_callback: Optional[Any] = None,
) -> CurationRunResult:
    """Run the full curation pipeline over a raw activity CSV's rows.

    Args:
        raw_rows: Every row from a raw ChEMBL-shaped activity CSV, as
            produced by ``csv.DictReader`` (or an equivalent synthetic
            fixture with the same column names).
        source_dataset_id: The raw dataset's identifier, used to build
            deterministic ``measurement_id``s.
        endpoint: The endpoint identifier.
        license_resolution: This run's (single, source-level) licence
            resolution — applied to every row, since today's live
            endpoints are each single-source.
        bad_validity_flags: The endpoint-specific set of
            ``data_validity_comment`` values to treat as unreliable — see
            :func:`drugsim_curation.ledger.build_ledger_row`'s own
            docstring on why this is per-endpoint, not global.
        assay_metadata_by_id: Pre-resolved assay context, keyed by
            ``assay_chembl_id`` — callers fetch this once (see
            :func:`drugsim_curation.assay_context.fetch_assay_metadata`)
            rather than this function doing any network I/O itself.
        blocker_threshold_nm: The binary-label cutoff, in nM.
        dataset_version: This run's dataset version string.
        retrieved_at: The raw dataset's retrieval date.
        curated_at: This run's timestamp.
        progress_callback: Optional ``callable(done: int, total: int)``,
            invoked periodically during structure standardisation — the
            slowest step for a large raw pull. ``None`` means no progress
            reporting.

    Returns:
        The full curation result, both lists sorted by their own id for
        deterministic, diff-friendly output.
    """
    by_molecule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in raw_rows:
        by_molecule[r["molecule_chembl_id"]].append(r)

    structure_by_molecule: dict[str, tuple[str, Any, Optional[str]]] = {}
    for i, (mol_id, mol_rows) in enumerate(by_molecule.items(), 1):
        if progress_callback is not None:
            progress_callback(i, len(by_molecule))
        smiles = mol_rows[0]["canonical_smiles"]
        try:
            processed = process_structure(smiles)
        except StructureError as exc:
            structure_by_molecule[mol_id] = ("invalid_quarantined", None, str(exc))
            continue
        structure_by_molecule[mol_id] = ("mixture_excluded" if processed.is_mixture else "valid", processed, None)

    ledger_rows: list[MeasurementLedgerRow] = []
    for r in raw_rows:
        mol_id = r["molecule_chembl_id"]
        structure_status, processed, structure_error = structure_by_molecule[mol_id]
        compound_id = processed.identity.inchikey_full if structure_status == "valid" else None
        mw = processed.descriptors.mw_g_mol if (processed is not None and processed.descriptors is not None) else None
        unit_resolution = resolve_unit(r.get("standard_value", ""), r.get("standard_units", ""), molecular_weight_g_mol=mw)
        assay_metadata = assay_metadata_by_id.get(r.get("assay_chembl_id", ""))
        ledger_rows.append(
            build_ledger_row(
                r,
                source_dataset_id=source_dataset_id,
                endpoint=endpoint,
                structure_status=structure_status,
                structure_error=structure_error,
                compound_id=compound_id,
                unit_resolution=unit_resolution,
                assay_metadata=assay_metadata,
                license_resolution=license_resolution,
                bad_validity_flags=bad_validity_flags,
                retrieved_at=retrieved_at,
                curated_at=curated_at,
            )
        )

    # Exact-duplicate tagging within each compound's included rows.
    by_compound: dict[str, list[MeasurementLedgerRow]] = defaultdict(list)
    for row in ledger_rows:
        by_compound[row.compound_id].append(row)
    for rows in by_compound.values():
        included = [r for r in rows if r.curation_status == "included"]
        patched = find_exact_duplicate_measurements(included)
        if patched:
            for i, row in enumerate(ledger_rows):
                if row.measurement_id in patched:
                    ledger_rows[i] = patched[row.measurement_id]

    # Compound-level aggregation, only for resolved (valid-structure) entities.
    by_compound = defaultdict(list)
    for row in ledger_rows:
        by_compound[row.compound_id].append(row)

    structure_by_ik = {
        proc.identity.inchikey_full: proc for status, proc, _ in structure_by_molecule.values() if status == "valid"
    }

    curated_compounds: list[CuratedCompoundRow] = []
    conflict_patch: dict[str, str] = {}
    for compound_id, rows in by_compound.items():
        if compound_id.startswith("UNRESOLVED:"):
            continue
        processed = structure_by_ik[compound_id]
        curated = build_curated_compound(
            compound_id=compound_id,
            canonical_smiles=processed.identity.canonical_smiles,
            standardized_smiles=processed.standardized_smiles,
            bemis_murcko_scaffold=processed.identity.bemis_murcko_scaffold or "",
            molecular_formula=processed.identity.molecular_formula,
            ledger_rows=rows,
            is_potency=True,
            blocker_threshold_nm=blocker_threshold_nm,
            dataset_version=dataset_version,
            curated_at=curated_at,
        )
        curated_compounds.append(curated)
        for mid in curated.measurement_ids.split(";") if curated.measurement_ids else []:
            conflict_patch[mid] = curated.conflict_status

    # Patch conflict_status back onto the contributing ledger rows now that
    # aggregation has decided it.
    for i, row in enumerate(ledger_rows):
        if row.measurement_id in conflict_patch:
            ledger_rows[i] = dataclasses.replace(row, conflict_status=conflict_patch[row.measurement_id])
        elif row.curation_status == "included":
            ledger_rows[i] = dataclasses.replace(row, conflict_status="not_aggregated")
        else:
            ledger_rows[i] = dataclasses.replace(row, conflict_status="not_applicable")

    ledger_rows.sort(key=lambda r: r.measurement_id)
    curated_compounds.sort(key=lambda c: c.compound_id)

    return CurationRunResult(ledger_rows=ledger_rows, curated_compounds=curated_compounds)
