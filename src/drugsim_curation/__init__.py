"""DrugSim scientific data curation: per-measurement ledger, resolved
compound view, explainable quality score, and curation reporting.

Builds on top of ``drugsim_chem`` (structure standardisation) and
``drugsim_quality`` (aggregation, licence audit) rather than duplicating
either. Produces a new, additive artifact under ``datasets/curated/`` —
never modifies ``datasets/processed/*.csv``, ``*.npz``, or anything the
live ADMET models actually train on. See
``docs/data-curation/README.md`` for the pipeline overview and
``docs/data-curation/rules.md`` for every rule this package implements.

Modules:
    units: Per-record unit resolution — molar units convert on a fixed
        factor; mass-concentration units need a molecular weight or are
        marked unresolved; nothing is guessed.
    assay_context: Organism/cell-type/paradigm enrichment via a cached,
        generic-over-target ChEMBL assay lookup.
    provenance: Per-record licence resolution against
        ``datasets/registry.yaml``, failing closed on anything unresolved.
    ledger: The per-measurement curation ledger — one row per raw
        measurement, including everything the live pipelines currently
        drop, with an explicit curation_status/exclusion_reason.
    curated_view: The per-compound resolved/aggregate view. Discordant
        compounds are retained with ``training_eligible=False``, never
        silently dropped.
    quality_score: The explainable 0-1 data-quality score — a weighted sum
        of named, inspectable components, never an opaque model output.
    report: Builds the JSON curation report (funnel + exclusion reasons)
        for one endpoint's run.
    pipeline: The shared orchestration (raw rows in, ledger + curated
        compounds out) that every driver script and the golden fixture
        generator/test call, so the sequence exists in exactly one place.
"""

from __future__ import annotations

from drugsim_curation.assay_context import (
    ASSAY_CONTEXT_UNAVAILABLE_FIELDS,
    AssayMetadata,
    classify_assay_paradigm,
    fetch_assay_metadata,
)
from drugsim_curation.curated_view import CuratedCompoundRow, build_curated_compound
from drugsim_curation.ledger import MeasurementLedgerRow, build_ledger_row, find_exact_duplicate_measurements
from drugsim_curation.pipeline import CurationRunResult, curate_raw_rows
from drugsim_curation.provenance import LicenseResolution, SourceRegistry, resolve_license
from drugsim_curation.quality_score import QUALITY_SCORE_WEIGHTS, QualityScoreBreakdown, compute_quality_score
from drugsim_curation.report import build_curation_report
from drugsim_curation.units import UnitResolution, resolve_unit
from drugsim_curation.versions import CURATION_PIPELINE_VERSION

__all__ = [
    "ASSAY_CONTEXT_UNAVAILABLE_FIELDS",
    "CURATION_PIPELINE_VERSION",
    "QUALITY_SCORE_WEIGHTS",
    "AssayMetadata",
    "CurationRunResult",
    "CuratedCompoundRow",
    "LicenseResolution",
    "MeasurementLedgerRow",
    "QualityScoreBreakdown",
    "SourceRegistry",
    "UnitResolution",
    "build_curated_compound",
    "build_curation_report",
    "build_ledger_row",
    "classify_assay_paradigm",
    "compute_quality_score",
    "curate_raw_rows",
    "fetch_assay_metadata",
    "find_exact_duplicate_measurements",
    "resolve_license",
    "resolve_unit",
]
