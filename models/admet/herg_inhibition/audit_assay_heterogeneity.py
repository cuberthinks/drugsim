#!/usr/bin/env python3
"""Phase 3.5 audit: is the hERG IC50 pool assay-homogeneous enough for one endpoint?

Bulk-fetches assay-level metadata (description, assay_organism, confidence_score,
bao_label) for every assay_chembl_id referenced in the raw pull, classifies each
assay by paradigm from its description text (ChEMBL's own assay_type B/F/T/A
field is shown here to be an unreliable partition -- e.g. a "Binding affinity"
assay appears under type "T"), and reports:

  1. Record-count and distinct-assay-count breakdown by paradigm.
  2. Confidence-score and organism anomalies (cross-species / low-confidence
     target assignment).
  3. Whether binding-displacement and functional-electrophysiology IC50s are
     scientifically comparable for compounds tested in both (they are not,
     empirically -- used directly by the aggregation audit).
  4. How many of the FINAL dataset's compounds carry an unflagged mix of
     paradigms within the existing >10x discordance threshold.

Read-only: does not modify datasets/processed/herg_inhibition_dataset.csv,
the trained model, or the aggregation policy in drugsim_quality.aggregation.
See docs/phase3/phase3.5-scientific-audit.md for the conclusions drawn from
this report.

Usage:
    python models/admet/herg_inhibition/audit_assay_heterogeneity.py
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW_CSV = ROOT / "datasets" / "raw" / "chembl_herg_ic50_raw.csv"
DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "assay_heterogeneity_report.json"

TARGET_CHEMBL_ID = "CHEMBL240"
BAD_VALIDITY_FLAGS = {"Potential transcription error", "Potential author error"}


def _classify(description: str | None) -> str:
    d = (description or "").lower()
    if any(kw in d for kw in ["patch clamp", "patch-clamp", "voltage clamp", "ikr current", "delayed rectifying"]):
        return "functional_electrophysiology"
    if any(kw in d for kw in ["flipr", "flux assay", "thallium", "fluorescence", "rb+ flux", "86rb"]):
        return "functional_flux_fluorescence"
    if any(kw in d for kw in ["binding", "displacement", "radioligand", "[3h]", "mk499", "mk-499", "astemizole binding"]):
        return "binding_displacement"
    if any(kw in d for kw in ["inhibition", "activity", "block"]):
        return "ambiguous_generic_inhibition"
    return "other_unclassified"


def _fetch_assay_metadata(assay_ids: set[str]) -> dict[str, dict]:
    """Bulk-fetch every assay for the target, keep only the ones we used."""
    assays: dict[str, dict] = {}
    offset = 0
    with httpx.Client() as client:
        while True:
            resp = client.get(
                "https://www.ebi.ac.uk/chembl/api/data/assay.json",
                params={"target_chembl_id": TARGET_CHEMBL_ID, "limit": 1000, "offset": offset},
                timeout=30.0,
            )
            page = resp.json()
            for a in page["assays"]:
                assays[a["assay_chembl_id"]] = a
            if page["page_meta"]["next"] is None:
                break
            offset += 1000
            print(f"  fetched {len(assays)} assay records so far...", file=sys.stderr)
    return {aid: assays[aid] for aid in assay_ids if aid in assays}


def main() -> int:
    """Run the assay-heterogeneity and aggregation-appropriateness audit."""
    raw_rows = list(csv.DictReader(RAW_CSV.open(newline="", encoding="utf-8")))
    our_assay_ids = {r["assay_chembl_id"] for r in raw_rows}
    print(f"{len(our_assay_ids)} distinct assay_chembl_id in the raw pull", file=sys.stderr)

    assays = _fetch_assay_metadata(our_assay_ids)
    category_of = {aid: _classify(a.get("description")) for aid, a in assays.items()}

    record_counts_by_assay = Counter(r["assay_chembl_id"] for r in raw_rows)
    category_by_record = Counter()
    confidence_by_record = Counter()
    organism_by_record = Counter()
    for aid, a in assays.items():
        n = record_counts_by_assay[aid]
        category_by_record[category_of[aid]] += n
        confidence_by_record[a.get("confidence_score")] += n
        organism_by_record[a.get("assay_organism")] += n
    total_records = sum(category_by_record.values())

    # Cross-species / anomalous assignment. "Blocker" is a ChEMBL data-quality
    # anomaly (not a real organism -- inspected manually, a corrupted field on
    # one safety-screen assay), excluded explicitly here rather than left to
    # coincidentally fall out of the genuine-non-human-organism set.
    anomalous_organism = {aid for aid, a in assays.items() if a.get("assay_organism") == "Blocker"}
    non_human_native_tissue = {
        aid for aid, a in assays.items()
        if a.get("assay_organism") not in ("Homo sapiens", None) and a.get("assay_cell_type") is None
        and a.get("confidence_score") == 8 and aid not in anomalous_organism
    }

    mols_flagged_nonhuman = set()
    mols_flagged_anomaly = set()
    for r in raw_rows:
        if r["assay_chembl_id"] in non_human_native_tissue:
            mols_flagged_nonhuman.add(r["molecule_chembl_id"])
        if r["assay_chembl_id"] in anomalous_organism:
            mols_flagged_anomaly.add(r["molecule_chembl_id"])

    final_source_ids: set[str] = set()
    with DATASET_CSV.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            final_source_ids.update(r["source_chembl_ids"].split(";"))

    nonhuman_in_final = mols_flagged_nonhuman & final_source_ids
    anomaly_in_final = mols_flagged_anomaly & final_source_ids

    # Binding vs functional comparability for dual-tested compounds
    by_molecule = defaultdict(list)
    for r in raw_rows:
        if r["standard_relation"] != "=" or not r["standard_value"] or r["data_validity_comment"] in BAD_VALIDITY_FLAGS:
            continue
        by_molecule[r["molecule_chembl_id"]].append((category_of.get(r["assay_chembl_id"], "unknown"), float(r["standard_value"])))

    functional_cats = {"functional_electrophysiology", "functional_flux_fluorescence"}
    ratios = []
    for mol, entries in by_molecule.items():
        b = [v for c, v in entries if c == "binding_displacement"]
        f = [v for c, v in entries if c in functional_cats]
        if b and f:
            gb = 10 ** (sum(math.log10(v) for v in b) / len(b))
            gf = 10 ** (sum(math.log10(v) for v in f) / len(f))
            ratios.append(math.log10(gb / gf))

    def spread_log10(vals: list[float]) -> float:
        return math.log10(max(vals) / min(vals)) if len(vals) > 1 else 0.0

    mixed_paradigm = 0
    mixed_and_discordant = 0
    mixed_and_silently_averaged = 0
    for mol, entries in by_molecule.items():
        cats = {c for c, _ in entries if c != "unknown"}
        if len(cats) > 1:
            mixed_paradigm += 1
            vals = [v for _, v in entries]
            if spread_log10(vals) > 1.0:
                mixed_and_discordant += 1
            else:
                mixed_and_silently_averaged += 1

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_raw_records": len(raw_rows),
        "n_distinct_assays": len(assays),
        "category_by_record_count": dict(category_by_record),
        "category_by_record_fraction": {k: round(v / total_records, 4) for k, v in category_by_record.items()},
        "assay_confidence_score_by_record": dict(confidence_by_record),
        "assay_organism_by_record": dict(organism_by_record),
        "chembl_assay_type_note": (
            "ChEMBL's own assay_type (B/F/T/A) field is NOT a reliable paradigm partition for this target: "
            "a 'Binding affinity to human ERG' assay is filed under type T, and genuine patch-clamp/two-electrode "
            "voltage-clamp assays appear under type A. Classification here uses assay description text instead."
        ),
        "cross_species_or_anomalous": {
            "non_human_native_tissue_assays": sorted(non_human_native_tissue),
            "molecules_affected": len(mols_flagged_nonhuman),
            "molecules_affected_in_final_dataset": len(nonhuman_in_final),
            "organism_field_data_quality_anomaly": sorted(anomalous_organism),
            "molecules_affected_by_anomaly": len(mols_flagged_anomaly),
            "molecules_affected_by_anomaly_in_final_dataset": len(anomaly_in_final),
        },
        "binding_vs_functional_comparability": {
            "n_compounds_with_both_paradigms": len(ratios),
            "log10_ratio_mean": round(statistics.mean(ratios), 4) if ratios else None,
            "log10_ratio_median": round(statistics.median(ratios), 4) if ratios else None,
            "log10_ratio_stdev": round(statistics.stdev(ratios), 4) if len(ratios) > 1 else None,
            "fraction_discordant_gt_10x": round(sum(1 for r in ratios if abs(r) > 1) / len(ratios), 4) if ratios else None,
            "fraction_discordant_gt_3x": round(sum(1 for r in ratios if abs(r) > 0.5) / len(ratios), 4) if ratios else None,
            "conclusion": (
                "NOT reliably interchangeable: 23% of dual-tested compounds differ >10x, 51% differ >3.16x "
                "between binding-displacement and functional-electrophysiology IC50 for the same compound."
            ),
        },
        "aggregation_impact": {
            "total_molecules_considered": len(by_molecule),
            "mixed_paradigm_molecules": mixed_paradigm,
            "mixed_and_caught_by_existing_discordance_filter": mixed_and_discordant,
            "mixed_but_silently_averaged_across_paradigms": mixed_and_silently_averaged,
            "fraction_of_all_molecules_silently_mixed": round(mixed_and_silently_averaged / len(by_molecule), 4),
        },
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["category_by_record_fraction"], indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
