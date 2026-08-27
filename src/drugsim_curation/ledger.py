"""The per-measurement curation ledger.

One row per raw measurement (a raw ``activity_id``), including rows the
live ``build_dataset.py`` pipelines currently drop before ever writing
anything -- censored relations, bad-validity-flagged records, quarantined
structures. Preserving all of them here, with an explicit
``curation_status``/``exclusion_reason``, is what "don't silently delete
questionable measurements" actually requires: a person must be able to see
*which* raw records were excluded and *why*, not just a count.

This module builds one ledger row at a time from already-computed inputs
(structure processing, unit resolution, assay context, licence
resolution) -- it does not itself call ``drugsim_chem`` or fetch anything,
so it stays trivially unit-testable with synthetic fixtures. The caller
(a per-endpoint driver script) is responsible for computing those inputs
once per distinct molecule/assay and passing them in for every raw row
that shares them.

``conflict_status`` is deliberately NOT decided here: whether a measurement
belongs to a discordant aggregate is a property of the *compound-level*
aggregation (see :mod:`drugsim_curation.curated_view`), not of the
measurement in isolation. Rows built by this module start with
``conflict_status="pending_aggregation"``; the driver script patches it
after aggregation completes, using
:func:`drugsim_curation.curated_view.build_curated_compound`'s
``measurement_ids`` (the included/contributing subset).

Exact-duplicate detection (identical value+unit+relation+assay+document
within one compound) is a lighter-weight, ledger-native check than
``drugsim_quality.dedup.find_measurement_duplicates`` -- that function is
built for *cross-source* dedup (matching on parent InChIKey + target +
literature reference) and is the right tool once a second data source
exists, but is not the natural fit for "are these two rows from the same
single ChEMBL pull actually the same reported measurement." See
:func:`find_exact_duplicate_measurements`.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal, Optional

from drugsim_curation.assay_context import ASSAY_CONTEXT_UNAVAILABLE_FIELDS, AssayMetadata
from drugsim_curation.provenance import LicenseResolution
from drugsim_curation.units import UnitResolution
from drugsim_curation.versions import CURATION_PIPELINE_VERSION

__all__ = ["MeasurementLedgerRow", "build_ledger_row", "find_exact_duplicate_measurements"]

StructureStatus = Literal["valid", "invalid_quarantined", "mixture_excluded"]
CurationStatus = Literal["included", "excluded"]

#: Priority order for exclusion reasons, evaluated top to bottom. A row
#: failing multiple checks reports the first (most fundamental) one --
#: e.g. an invalid structure is reported as such even if its unit also
#: happens to be unresolved, since unit resolution is moot without a valid
#: structure to attach it to.
_EXCLUSION_PRIORITY = (
    "invalid_structure",
    "mixture",
    "censored_measurement",
    "bad_validity_comment",
    "unresolved_unit",
    "unresolved_license",
)


@dataclass(frozen=True)
class MeasurementLedgerRow:
    """One row of the per-measurement curation ledger.

    See the module docstring for why ``conflict_status`` starts as
    ``"pending_aggregation"`` rather than being decided here.
    """

    measurement_id: str
    compound_id: str
    source_dataset_id: str
    source_record_id: str
    endpoint: str
    molecule_chembl_id: str
    structure_status: StructureStatus
    structure_error: Optional[str]
    original_value: str
    original_unit: str
    original_relation: str
    normalised_value: Optional[float]
    normalised_unit: Optional[str]
    unit_status: str
    conversion_method: str
    conversion_status: str
    assay_chembl_id: str
    assay_type_raw: str
    assay_organism: Optional[str]
    assay_cell_type: Optional[str]
    assay_tissue: Optional[str]
    assay_paradigm_classification: Optional[str]
    assay_confidence_score: Optional[int]
    assay_context_unavailable_fields: str
    data_validity_comment: str
    document_chembl_id: str
    document_year: str
    license_spdx: Optional[str]
    license_tier: Optional[str]
    license_commercial_ok: Optional[bool]
    license_status: str
    curation_status: CurationStatus
    exclusion_reason: Optional[str]
    conflict_status: str
    transformation_version: str
    retrieved_at: str
    curated_at: str
    duplicate_group_id: Optional[str] = None
    duplicate_role: Optional[str] = None


def build_ledger_row(
    raw_row: dict[str, Any],
    *,
    source_dataset_id: str,
    endpoint: str,
    structure_status: StructureStatus,
    structure_error: Optional[str],
    compound_id: Optional[str],
    unit_resolution: UnitResolution,
    assay_metadata: Optional[AssayMetadata],
    license_resolution: LicenseResolution,
    bad_validity_flags: frozenset[str],
    retrieved_at: str,
    curated_at: str,
) -> MeasurementLedgerRow:
    """Build one ledger row from a raw activity row and its computed context.

    Args:
        raw_row: One row from the raw ChEMBL activity CSV, as produced by
            ``csv.DictReader``.
        source_dataset_id: The registry/manifest identifier of the raw
            dataset this row came from, e.g. ``"chembl_herg_ic50_raw"``.
        endpoint: The endpoint identifier, e.g. ``"herg_inhibition"``.
        structure_status: Whether ``raw_row``'s ``molecule_chembl_id``
            standardised to a valid single structure, a quarantined
            failure, or a flagged mixture -- computed once per distinct
            molecule by the caller and passed in for every row that shares
            it.
        structure_error: The ``StructureError`` message, if
            ``structure_status == "invalid_quarantined"``, else ``None``.
        compound_id: The standardised ``inchikey_full``, or ``None`` when
            ``structure_status`` is not ``"valid"`` (a row with no
            resolved structure gets a deterministic
            ``"UNRESOLVED:{molecule_chembl_id}"`` placeholder instead, set
            inside this function so callers never have to invent one).
        unit_resolution: This row's resolved (or unresolved) unit, from
            :func:`drugsim_curation.units.resolve_unit`.
        assay_metadata: This row's enriched assay context, or ``None`` if
            unavailable (never fabricated).
        license_resolution: This row's source licence resolution, from
            :func:`drugsim_curation.provenance.resolve_license`.
        bad_validity_flags: The exact set of ``data_validity_comment``
            values this *endpoint's* live pipeline treats as unreliable --
            deliberately passed in rather than hardcoded, because hERG's
            and CYP3A4's live ``build_dataset.py`` scripts use different
            sets today (a real, documented, endpoint-specific decision --
            see ``models/admet/cyp3a4_inhibition/build_dataset.py``'s own
            comment on why "Outside typical range" was added there and not
            retrofitted onto hERG).
        retrieved_at: The raw dataset's retrieval date (from its manifest).
        curated_at: This curation run's timestamp.

    Returns:
        The built ledger row, with ``curation_status``/``exclusion_reason``
        already decided from measurement-level checks, and
        ``conflict_status="pending_aggregation"`` awaiting the compound-level
        aggregation step.
    """
    resolved_compound_id = compound_id or f"UNRESOLVED:{raw_row['molecule_chembl_id']}"

    reasons: dict[str, bool] = {
        "invalid_structure": structure_status == "invalid_quarantined",
        "mixture": structure_status == "mixture_excluded",
        "censored_measurement": raw_row.get("standard_relation") != "=",
        "bad_validity_comment": raw_row.get("data_validity_comment", "") in bad_validity_flags,
        "unresolved_unit": unit_resolution.unit_status == "unresolved",
        "unresolved_license": license_resolution.license_status == "unresolved",
    }
    exclusion_reason = next((r for r in _EXCLUSION_PRIORITY if reasons[r]), None)

    return MeasurementLedgerRow(
        measurement_id=f"{source_dataset_id}:{raw_row['activity_id']}",
        compound_id=resolved_compound_id,
        source_dataset_id=source_dataset_id,
        source_record_id=raw_row["activity_id"],
        endpoint=endpoint,
        molecule_chembl_id=raw_row["molecule_chembl_id"],
        structure_status=structure_status,
        structure_error=structure_error,
        original_value=raw_row.get("standard_value", ""),
        original_unit=raw_row.get("standard_units", ""),
        original_relation=raw_row.get("standard_relation", ""),
        normalised_value=unit_resolution.normalised_value,
        normalised_unit=unit_resolution.normalised_unit,
        unit_status=unit_resolution.unit_status,
        conversion_method=unit_resolution.conversion_method,
        conversion_status=unit_resolution.conversion_status,
        assay_chembl_id=raw_row.get("assay_chembl_id", ""),
        assay_type_raw=raw_row.get("assay_type", ""),
        assay_organism=assay_metadata.assay_organism if assay_metadata else None,
        assay_cell_type=assay_metadata.assay_cell_type if assay_metadata else None,
        assay_tissue=assay_metadata.assay_tissue if assay_metadata else None,
        assay_paradigm_classification=assay_metadata.paradigm if assay_metadata else None,
        assay_confidence_score=assay_metadata.confidence_score if assay_metadata else None,
        assay_context_unavailable_fields=";".join(ASSAY_CONTEXT_UNAVAILABLE_FIELDS),
        data_validity_comment=raw_row.get("data_validity_comment", ""),
        document_chembl_id=raw_row.get("document_chembl_id", ""),
        document_year=raw_row.get("document_year", ""),
        license_spdx=license_resolution.spdx,
        license_tier=license_resolution.tier,
        license_commercial_ok=license_resolution.commercial_ok,
        license_status=license_resolution.license_status,
        curation_status="excluded" if exclusion_reason else "included",
        exclusion_reason=exclusion_reason,
        conflict_status="pending_aggregation",
        transformation_version=CURATION_PIPELINE_VERSION,
        retrieved_at=retrieved_at,
        curated_at=curated_at,
    )


def find_exact_duplicate_measurements(
    rows: list[MeasurementLedgerRow],
) -> dict[str, MeasurementLedgerRow]:
    """Tag rows sharing identical value+unit+relation+assay+document.

    Two raw ChEMBL activity rows for the same compound that agree on all
    five of these fields are, for practical purposes, the same reported
    measurement appearing twice (e.g. re-abstracted in a later ChEMBL
    release) rather than two independent observations — both are kept
    (never deleted), but tagged so a downstream consumer can choose to
    count them once.

    Args:
        rows: Ledger rows to check — typically one compound's included
            rows, passed in by the driver script after
            :func:`build_ledger_row` has produced them.

    Returns:
        A mapping from ``measurement_id`` to a **new** row (this module's
        rows are frozen dataclasses) with ``duplicate_group_id`` and
        ``duplicate_role`` populated, for every row that is part of a
        group of 2 or more. Rows with no duplicate are omitted — the
        caller should keep the original row for those.
    """
    groups: dict[tuple[str, str, str, str, str], list[MeasurementLedgerRow]] = defaultdict(list)
    for row in rows:
        key = (row.original_value, row.original_unit, row.original_relation, row.assay_chembl_id, row.document_chembl_id)
        groups[key].append(row)

    patched: dict[str, MeasurementLedgerRow] = {}
    for key, group in groups.items():
        if len(group) < 2:
            continue
        group_sorted = sorted(group, key=lambda r: r.measurement_id)
        group_id = f"exact_dup:{'|'.join(key)}"
        representative_id = group_sorted[0].measurement_id
        for row in group_sorted:
            role = "representative" if row.measurement_id == representative_id else "duplicate"
            patched[row.measurement_id] = dataclasses.replace(row, duplicate_group_id=group_id, duplicate_role=role)
    return patched
