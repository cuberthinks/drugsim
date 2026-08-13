#!/usr/bin/env python3
"""Phase 9 Sec 4 data quality audit for the CYP3A4 inhibition dataset.

Run BEFORE any model training. Reports on the built dataset
(cyp3a4_inhibition_dataset.csv) and cross-references the raw pull and the
build manifest for duplicate/discordance/quarantine figures already
computed by build_dataset.py, rather than recomputing them.

Usage:
    python models/admet/cyp3a4_inhibition/data_quality_audit.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DATASET_CSV = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_dataset.csv"
BUILD_MANIFEST = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_dataset_manifest.json"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "chembl_cyp3a4_ic50_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "data_quality_report.json"


def main() -> int:
    df = pd.read_csv(DATASET_CSV)
    build_manifest = json.loads(BUILD_MANIFEST.read_text(encoding="utf-8"))
    raw_manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))

    # --- Impossible / suspicious value checks ---
    impossible_ic50 = df[(df["aggregated_ic50_nm"] <= 0) | (df["aggregated_ic50_nm"].isna())]
    # An IC50 above 1 M (1e9 nM) is physically nonsensical for a real assay well.
    suspicious_high = df[df["aggregated_ic50_nm"] > 1e9]
    missing_scaffold = df[df["bemis_murcko_scaffold"].isna() | (df["bemis_murcko_scaffold"] == "")]
    duplicate_inchikeys = df["inchikey_full"].duplicated().sum()  # must be 0 -- one row per entity by construction

    year_counter: Counter = Counter()
    for years_field in df["source_document_years"].fillna(""):
        for y in str(years_field).split(";"):
            if y:
                year_counter[y] += 1

    n_scaffolds = df["bemis_murcko_scaffold"].replace("", pd.NA).nunique(dropna=True)
    n_acyclic = int((df["bemis_murcko_scaffold"] == "").sum())

    report = {
        "dataset_id": build_manifest["dataset_id"],
        "dataset_version": build_manifest["dataset_version"],
        "n_compounds": int(len(df)),
        "n_unique_structures_by_inchikey": int(df["inchikey_full"].nunique()),
        "duplicate_inchikeys_in_final_dataset": int(duplicate_inchikeys),
        "n_source_measurements_total": int(df["n_source_measurements"].sum()),
        "measurements_per_compound": {
            "min": int(df["n_source_measurements"].min()),
            "median": float(df["n_source_measurements"].median()),
            "max": int(df["n_source_measurements"].max()),
            "compounds_with_multiple_measurements": int((df["n_source_measurements"] > 1).sum()),
        },
        "raw_pipeline_accounting": {
            "raw_records_from_chembl_api": raw_manifest["total_records_from_api"],
            "raw_records_after_unit_filter_nm": raw_manifest["total_records_written"],
            "raw_records_after_censoring_and_validity_filter": None,  # logged by build step, not re-derivable here without raw CSV re-scan
            "distinct_chembl_molecule_ids_in_raw_pull": raw_manifest["distinct_compounds"],
            "quarantined_unparseable_structures": build_manifest["quarantine_count"],
            "mixtures_excluded": build_manifest["mixtures_excluded_count"],
            "discordant_entities_excluded_over_10x_spread": build_manifest["discordant_entities_excluded_count"],
            "final_compounds_after_all_filters": build_manifest["final_compound_count"],
        },
        "class_distribution": build_manifest["label_distribution"],
        "unit_distribution": {"nM": int(len(df)), "note": "single-unit dataset by construction -- fetch step filtered to standard_units=nM only, same as hERG"},
        "chemical_diversity": {
            "n_unique_bemis_murcko_scaffolds": int(n_scaffolds),
            "n_acyclic_compounds_no_scaffold": n_acyclic,
            "scaffold_to_compound_ratio": round(float(n_scaffolds) / len(df), 4) if len(df) else None,
        },
        "source_distribution_by_publication_year": dict(sorted(year_counter.items())),
        "impossible_or_suspicious_values": {
            "ic50_le_zero_or_nan": int(len(impossible_ic50)),
            "ic50_above_1_molar_equivalent": int(len(suspicious_high)),
            "rows_missing_scaffold_field_entirely": int(len(missing_scaffold)),
        },
        "leakage_checks_summary": (
            "One row per standardised entity (inchikey_full) by construction -- "
            "0 duplicate structures possible within this file. Cross-split "
            "leakage (train/calibration/validation/test) is checked separately "
            "in prepare_features.py's split-group assertion and "
            "check_leakage.py, not here."
        ),
        "assessment": (
            "PROCEED" if len(impossible_ic50) == 0 and len(suspicious_high) == 0 and duplicate_inchikeys == 0
            else "STOP -- impossible values or duplicate entities found, see fields above"
        ),
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0 if report["assessment"] == "PROCEED" else 1


if __name__ == "__main__":
    sys.exit(main())
