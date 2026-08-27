"""The curation report — one JSON file per run, hiding nothing.

Every curation run must be able to answer, without re-reading the raw
data: how many records went in, how many made it to a training-eligible
compound, and exactly why every excluded one was excluded. This module
computes that funnel and the exclusion-reason breakdown directly from the
ledger and curated-compound rows a driver script already built — it does
not recompute anything chemistry- or aggregation-related itself.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from drugsim_curation.assay_context import ASSAY_CONTEXT_UNAVAILABLE_FIELDS
from drugsim_curation.curated_view import CuratedCompoundRow
from drugsim_curation.ledger import MeasurementLedgerRow
from drugsim_curation.versions import CURATION_PIPELINE_VERSION

__all__ = ["build_curation_report"]

_REPORT_VERSION = "1.0"


def build_curation_report(
    *,
    endpoint: str,
    generated_at: str,
    raw_csv_path: str,
    raw_manifest_sha256: str,
    retrieval_date: str,
    ledger_rows: list[MeasurementLedgerRow],
    curated_compounds: list[CuratedCompoundRow],
    ledger_output: dict[str, str],
    curated_output: dict[str, str],
) -> dict[str, Any]:
    """Build the JSON-serialisable curation report for one endpoint's run.

    Args:
        endpoint: The endpoint identifier.
        generated_at: This report's generation timestamp.
        raw_csv_path: Repo-relative path to the raw CSV this run read.
        raw_manifest_sha256: The raw dataset's own checksum, chaining this
            report back to a specific raw pull.
        retrieval_date: The raw dataset's retrieval date.
        ledger_rows: Every measurement-level row this run produced.
        curated_compounds: Every compound-level row this run produced.
        ledger_output: ``{"path": ..., "sha256": ...}`` for the written
            ledger CSV.
        curated_output: ``{"path": ..., "sha256": ...}`` for the written
            curated-compounds CSV.

    Returns:
        A plain dict, ready for ``json.dumps`` — deliberately not a bespoke
        dataclass, since this function's only job is to shape already-
        computed data into the documented report schema
        (``docs/data-curation/quality-report.md``).
    """
    exclusion_counts = Counter(r.exclusion_reason for r in ledger_rows if r.exclusion_reason is not None)
    compound_exclusion_counts = Counter(c.exclusion_reason for c in curated_compounds if c.exclusion_reason is not None)

    n_valid_structures = sum(1 for r in ledger_rows if r.structure_status == "valid")
    n_invalid_structures = sum(1 for r in ledger_rows if r.structure_status == "invalid_quarantined")
    n_mixtures = sum(1 for r in ledger_rows if r.structure_status == "mixture_excluded")
    n_unit_resolved = sum(1 for r in ledger_rows if r.unit_status == "resolved")
    n_unit_unresolved = sum(1 for r in ledger_rows if r.unit_status == "unresolved")
    n_license_resolved = sum(1 for r in ledger_rows if r.license_status == "resolved")
    n_license_unresolved = sum(1 for r in ledger_rows if r.license_status == "unresolved")
    n_exact_dup_collapsed = sum(1 for r in ledger_rows if r.duplicate_role == "duplicate")

    n_eligible = sum(1 for c in curated_compounds if c.training_eligible)
    n_ineligible = sum(1 for c in curated_compounds if not c.training_eligible)
    n_discordant_compounds = sum(1 for c in curated_compounds if c.conflict_status == "discordant")
    n_consistent_compounds = sum(1 for c in curated_compounds if c.conflict_status == "consistent")

    scores = [c.quality.total for c in curated_compounds]
    if scores:
        score_distribution = {
            "mean": round(statistics.mean(scores), 4),
            "median": round(statistics.median(scores), 4),
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
        }
    else:
        score_distribution = {"mean": None, "median": None, "min": None, "max": None}

    n_with_organism_or_paradigm = sum(
        1 for r in ledger_rows if r.curation_status == "included" and (r.assay_organism is not None or r.assay_paradigm_classification is not None)
    )
    n_included = sum(1 for r in ledger_rows if r.curation_status == "included")

    return {
        "report_version": _REPORT_VERSION,
        "endpoint": endpoint,
        "generated_at": generated_at,
        "curation_pipeline_version": CURATION_PIPELINE_VERSION,
        "source": {
            "raw_csv": raw_csv_path,
            "raw_manifest_sha256": raw_manifest_sha256,
            "retrieval_date": retrieval_date,
        },
        "funnel": {
            "raw_records": len(ledger_rows),
            "valid_structures": n_valid_structures,
            "invalid_structures_quarantined": n_invalid_structures,
            "mixtures_excluded": n_mixtures,
            "standardized_entities": len({r.compound_id for r in ledger_rows if r.structure_status == "valid"}),
            "unit_resolved_records": n_unit_resolved,
            "unit_unresolved_records": n_unit_unresolved,
            "license_resolved_records": n_license_resolved,
            "license_unresolved_records": n_license_unresolved,
            "exact_duplicate_records_collapsed": n_exact_dup_collapsed,
            "conflict_consistent_compounds": n_consistent_compounds,
            "conflict_discordant_compounds": n_discordant_compounds,
            "training_eligible_compounds": n_eligible,
            "training_ineligible_compounds": n_ineligible,
        },
        "exclusion_reasons": {
            "measurement_level": dict(sorted(exclusion_counts.items())),
            "compound_level": dict(sorted(compound_exclusion_counts.items())),
        },
        "quality_score_distribution": score_distribution,
        "assay_context_coverage": {
            "fraction_with_organism_or_paradigm": (round(n_with_organism_or_paradigm / n_included, 4) if n_included else None),
            "unavailable_dimensions": list(ASSAY_CONTEXT_UNAVAILABLE_FIELDS),
        },
        "outputs": {
            "ledger_csv": ledger_output,
            "curated_compounds_csv": curated_output,
        },
    }
