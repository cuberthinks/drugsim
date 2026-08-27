#!/usr/bin/env python3
"""Curate the CYP3A4 raw ChEMBL pull into a per-measurement ledger + curated view.

Mirrors ``models/admet/herg_inhibition/curate_measurements.py`` exactly --
same pipeline (via the shared ``drugsim_curation.pipeline.curate_raw_rows``),
same output shape -- differing only in the constants below. See that
script's module docstring for the full rationale; it is not repeated here.

One deliberate difference worth calling out explicitly: ``BAD_VALIDITY_FLAGS``
includes ``"Outside typical range"`` here but not in hERG's script, mirroring
the same real, documented, endpoint-specific decision already made in
``build_dataset.py`` (see that file's comment on the Phase 9 data-quality
finding) -- not a divergence introduced by this curation layer.

Usage:
    python models/admet/cyp3a4_inhibition/curate_measurements.py
    python models/admet/cyp3a4_inhibition/curate_measurements.py --no-network
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import httpx  # noqa: E402

from drugsim_curation import (  # noqa: E402
    SourceRegistry,
    build_curation_report,
    curate_raw_rows,
    fetch_assay_metadata,
    resolve_license,
)

ROOT = Path(__file__).resolve().parents[3]
RAW_CSV = ROOT / "datasets" / "raw" / "chembl_cyp3a4_ic50_raw.csv"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "chembl_cyp3a4_ic50_manifest.json"
REGISTRY_YAML = ROOT / "datasets" / "registry.yaml"
ASSAY_CACHE = ROOT / "datasets" / "reference" / "chembl_cyp3a4_assay_metadata_cache.json"
OUT_DIR = ROOT / "datasets" / "curated"
LEDGER_CSV = OUT_DIR / "cyp3a4_inhibition_measurements_ledger.csv"
CURATED_CSV = OUT_DIR / "cyp3a4_inhibition_curated_compounds.csv"
REPORT_JSON = OUT_DIR / "cyp3a4_inhibition_curation_report.json"
MANIFEST_JSON = OUT_DIR / "cyp3a4_inhibition_curation_manifest.json"

ENDPOINT = "cyp3a4_inhibition"
SOURCE_DATASET_ID = "chembl_cyp3a4_ic50_raw"
SOURCE_ID = "chembl"
TARGET_CHEMBL_ID = "CHEMBL340"

#: Mirrors build_dataset.py's own exclusion set for THIS endpoint exactly --
#: includes "Outside typical range", unlike hERG's script. See module docstring.
BAD_VALIDITY_FLAGS = frozenset({"Potential transcription error", "Potential author error", "Outside typical range"})

#: Same convention as hERG: 10 uM.
INHIBITOR_THRESHOLD_NM = 10_000.0

CURATED_FIELDS_FLAT = [
    "compound_id", "inchikey_full", "canonical_smiles", "standardized_smiles", "bemis_murcko_scaffold",
    "molecular_formula", "n_source_measurements_total", "n_source_measurements_used", "aggregated_ic50_nm",
    "aggregation_method", "value_spread_log10", "is_discordant", "conflict_status", "label", "training_eligible",
    "exclusion_reason", "data_quality_score", "qs_structure_validity", "qs_unit_resolution_rate",
    "qs_license_resolution", "qs_measurement_consistency", "qs_duplicate_resolution", "qs_assay_context_coverage",
    "qs_provenance_completeness", "measurement_ids", "source_chembl_ids", "source_document_years",
    "molecule_pref_names", "license_spdx", "license_tier", "license_commercial_ok", "dataset_version", "curated_at",
]


def _curated_row_dict(c) -> dict:
    return {
        "compound_id": c.compound_id,
        "inchikey_full": c.inchikey_full,
        "canonical_smiles": c.canonical_smiles,
        "standardized_smiles": c.standardized_smiles,
        "bemis_murcko_scaffold": c.bemis_murcko_scaffold,
        "molecular_formula": c.molecular_formula,
        "n_source_measurements_total": c.n_source_measurements_total,
        "n_source_measurements_used": c.n_source_measurements_used,
        "aggregated_ic50_nm": c.aggregated_ic50_nm,
        "aggregation_method": c.aggregation_method,
        "value_spread_log10": c.value_spread_log10,
        "is_discordant": c.is_discordant,
        "conflict_status": c.conflict_status,
        "label": c.label,
        "training_eligible": c.training_eligible,
        "exclusion_reason": c.exclusion_reason,
        "data_quality_score": c.quality.total,
        "qs_structure_validity": c.quality.structure_validity,
        "qs_unit_resolution_rate": c.quality.unit_resolution_rate,
        "qs_license_resolution": c.quality.license_resolution,
        "qs_measurement_consistency": c.quality.measurement_consistency,
        "qs_duplicate_resolution": c.quality.duplicate_resolution,
        "qs_assay_context_coverage": c.quality.assay_context_coverage,
        "qs_provenance_completeness": c.quality.provenance_completeness,
        "measurement_ids": c.measurement_ids,
        "source_chembl_ids": c.source_chembl_ids,
        "source_document_years": c.source_document_years,
        "molecule_pref_names": c.molecule_pref_names,
        "license_spdx": c.license_spdx,
        "license_tier": c.license_tier,
        "license_commercial_ok": c.license_commercial_ok,
        "dataset_version": c.dataset_version,
        "curated_at": c.curated_at,
    }


def main() -> int:
    """Run the curation pipeline for CYP3A4 and write all outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true", help="use only the local assay-metadata cache")
    args = parser.parse_args()

    curated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw_manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    retrieved_at = raw_manifest["retrieval_date"]

    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    print(f"loaded {len(raw_rows)} raw records (including censored/flagged -- none dropped here)", file=sys.stderr)

    registry = SourceRegistry.load(REGISTRY_YAML)
    license_resolution = resolve_license(registry, SOURCE_ID)
    print(f"licence for {SOURCE_ID!r}: {license_resolution.license_status}", file=sys.stderr)

    assay_ids = {r["assay_chembl_id"] for r in raw_rows if r.get("assay_chembl_id")}
    http_client = None if args.no_network else httpx.Client()
    try:
        assay_metadata_by_id = fetch_assay_metadata(
            TARGET_CHEMBL_ID, assay_ids, cache_path=ASSAY_CACHE, http_client=http_client
        )
    finally:
        if http_client is not None:
            http_client.close()
    print(f"resolved assay context for {len(assay_metadata_by_id)}/{len(assay_ids)} distinct assays", file=sys.stderr)

    def _progress(done: int, total: int) -> None:
        if done % 3000 == 0:
            print(f"  standardised {done}/{total} molecules", file=sys.stderr)

    result = curate_raw_rows(
        raw_rows,
        source_dataset_id=SOURCE_DATASET_ID,
        endpoint=ENDPOINT,
        license_resolution=license_resolution,
        bad_validity_flags=BAD_VALIDITY_FLAGS,
        assay_metadata_by_id=assay_metadata_by_id,
        blocker_threshold_nm=INHIBITOR_THRESHOLD_NM,
        dataset_version="v1",
        retrieved_at=retrieved_at,
        curated_at=curated_at,
        progress_callback=_progress,
    )
    ledger_rows, curated_compounds = result.ledger_rows, result.curated_compounds

    n_eligible = sum(1 for c in curated_compounds if c.training_eligible)
    n_discordant = sum(1 for c in curated_compounds if c.conflict_status == "discordant")
    print(
        f"resolved {len(raw_rows)} raw rows to {len(curated_compounds)} compounds "
        f"({n_eligible} training-eligible, {n_discordant} discordant)",
        file=sys.stderr,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ledger_fields = [f.name for f in dataclasses.fields(ledger_rows[0])] if ledger_rows else []
    with LEDGER_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ledger_fields)
        writer.writeheader()
        for row in ledger_rows:
            writer.writerow(dataclasses.asdict(row))

    with CURATED_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CURATED_FIELDS_FLAT)
        writer.writeheader()
        for c in curated_compounds:
            writer.writerow(_curated_row_dict(c))

    ledger_sha256 = hashlib.sha256(LEDGER_CSV.read_bytes()).hexdigest()
    curated_sha256 = hashlib.sha256(CURATED_CSV.read_bytes()).hexdigest()

    report = build_curation_report(
        endpoint=ENDPOINT,
        generated_at=curated_at,
        raw_csv_path=str(RAW_CSV.relative_to(ROOT)),
        raw_manifest_sha256=raw_manifest["output_sha256"],
        retrieval_date=retrieved_at,
        ledger_rows=ledger_rows,
        curated_compounds=curated_compounds,
        ledger_output={"path": str(LEDGER_CSV.relative_to(ROOT)), "sha256": ledger_sha256},
        curated_output={"path": str(CURATED_CSV.relative_to(ROOT)), "sha256": curated_sha256},
    )
    REPORT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "dataset_id": f"{ENDPOINT}_curated",
        "dataset_version": "v1",
        "endpoint": ENDPOINT,
        "curated_at": curated_at,
        "source_manifest": {
            "path": str(RAW_MANIFEST.relative_to(ROOT)),
            "output_sha256": raw_manifest["output_sha256"],
            "retrieval_date": retrieved_at,
        },
        "outputs": {
            "ledger_csv": {"path": str(LEDGER_CSV.relative_to(ROOT)), "sha256": ledger_sha256},
            "curated_compounds_csv": {"path": str(CURATED_CSV.relative_to(ROOT)), "sha256": curated_sha256},
            "report_json": {"path": str(REPORT_JSON.relative_to(ROOT))},
        },
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(ledger_rows)} ledger rows to {LEDGER_CSV}")
    print(f"wrote {len(curated_compounds)} curated compounds to {CURATED_CSV}")
    print(f"report: {REPORT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
