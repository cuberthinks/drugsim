#!/usr/bin/env python3
"""Build the DRD2 binding-affinity training dataset from the raw ChEMBL pull.

Mirrors `models/admet/herg_inhibition/build_dataset.py`'s structure and
reuses the same Phase 2 code (`drugsim_chem.process_structure`,
`drugsim_quality.aggregation.aggregate_continuous`) -- standardisation,
duplicate/salt-form merging by inchikey_full, and discordance-aware
geometric-mean aggregation are unchanged from the existing ADMET
pipelines.

**The one real difference from hERG/CYP3A4**: this is a regression
target, not a binary classification. Per
`docs/psychiatric-pipeline/scientific-foundation.md`'s selectivity
section, a downstream selectivity comparison needs a genuine,
direction-correct continuous affinity value -- so this script keeps the
aggregated Ki (nM) AND its pKi transform (pKi = 9 - log10(Ki_nM), i.e.
-log10(Ki in molar); higher pKi = stronger binding) as the training
label, and does not binarise at a threshold the way hERG/CYP3A4 do.

Usage:
    python models/psychiatric/drd2_activity/build_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from drugsim_chem import process_structure  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402
from drugsim_core.ids import generate_ulid  # noqa: E402
from drugsim_quality.aggregation import aggregate_continuous  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RAW_CSV = ROOT / "datasets" / "raw" / "chembl_drd2_ki_raw.csv"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "chembl_drd2_ki_manifest.json"
OUTPUT_CSV = ROOT / "datasets" / "processed" / "drd2_activity_dataset.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "processed" / "drd2_activity_dataset_manifest.json"

DATASET_ID = "drd2_activity"
DATASET_VERSION = "v1"

#: Records ChEMBL itself flags as unreliable -- excluded, not down-weighted.
#: Identical to hERG's own set; CYP3A4 additionally excludes "Outside typical
#: range" (an endpoint-specific choice documented there) -- not applied here
#: since it hasn't been evaluated for this endpoint yet.
_BAD_VALIDITY_FLAGS = {"Potential transcription error", "Potential author error"}


def _ki_nm_to_pki(ki_nm: float) -> float:
    """pKi = -log10(Ki in molar) = 9 - log10(Ki in nM). Higher = stronger binding."""
    return 9.0 - math.log10(ki_nm)


def _load_filtered_raw_rows() -> list[dict[str, Any]]:
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    kept = [
        r
        for r in rows
        if r["standard_relation"] == "="
        and r["data_validity_comment"] not in _BAD_VALIDITY_FLAGS
        and r["standard_value"]
        and float(r["standard_value"]) > 0  # log-transform requires a positive value
    ]
    return kept


def main() -> int:
    """Run the full dataset-build pipeline and write outputs."""
    raw_manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    rows = _load_filtered_raw_rows()
    print(f"loaded {len(rows)} uncensored, non-error-flagged, positive-value raw records", file=sys.stderr)

    by_molecule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_molecule[r["molecule_chembl_id"]].append(r)

    quarantined: list[tuple[str, str, str]] = []
    mixtures_excluded: list[str] = []
    by_entity: dict[str, dict[str, Any]] = {}

    for i, (mol_id, mol_rows) in enumerate(by_molecule.items(), 1):
        if i % 2000 == 0:
            print(f"  standardised {i}/{len(by_molecule)} molecules", file=sys.stderr)
        smiles = mol_rows[0]["canonical_smiles"]
        try:
            processed = process_structure(smiles)
        except StructureError as exc:
            quarantined.append((mol_id, smiles, str(exc)))
            continue

        if processed.is_mixture:
            mixtures_excluded.append(mol_id)
            continue

        ik = processed.identity.inchikey_full
        entity = by_entity.setdefault(
            ik,
            {
                "processed": processed,
                "values_nm": [],
                "source_chembl_ids": set(),
                "source_document_years": set(),
                "pref_names": set(),
            },
        )
        for r in mol_rows:
            entity["values_nm"].append(float(r["standard_value"]))
        entity["source_chembl_ids"].add(mol_id)
        for r in mol_rows:
            if r["document_year"]:
                entity["source_document_years"].add(r["document_year"])
            if r["molecule_pref_name"]:
                entity["pref_names"].add(r["molecule_pref_name"])

    print(
        f"resolved {len(by_molecule)} ChEMBL molecule ids to {len(by_entity)} "
        f"standardised entities ({len(quarantined)} quarantined, "
        f"{len(mixtures_excluded)} mixtures excluded)",
        file=sys.stderr,
    )

    dataset_rows = []
    discordant_count = 0
    for ik, entity in by_entity.items():
        agg = aggregate_continuous(entity["values_nm"], is_potency=True)
        if agg.is_discordant:
            discordant_count += 1
            continue

        processed = entity["processed"]
        pki = _ki_nm_to_pki(agg.aggregated_value)
        dataset_rows.append(
            {
                "local_compound_id": generate_ulid(),
                "inchikey_full": ik,
                "canonical_smiles": processed.identity.canonical_smiles,
                "standardized_smiles": processed.standardized_smiles,
                "bemis_murcko_scaffold": processed.identity.bemis_murcko_scaffold or "",
                "molecular_formula": processed.identity.molecular_formula,
                "n_source_measurements": agg.n_source_measurements,
                "n_source_chembl_ids": len(entity["source_chembl_ids"]),
                "aggregated_ki_nm": round(agg.aggregated_value, 4),
                "pki": round(pki, 4),
                "value_spread_log10": agg.value_spread_log10,
                "source_chembl_ids": ";".join(sorted(entity["source_chembl_ids"])),
                "source_document_years": ";".join(sorted(entity["source_document_years"])),
                "molecule_pref_names": ";".join(sorted(entity["pref_names"])),
            }
        )

    dataset_rows.sort(key=lambda r: r["inchikey_full"])

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dataset_rows[0].keys()) if dataset_rows else []
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset_rows)

    pki_values = [r["pki"] for r in dataset_rows]
    checksum = hashlib.sha256(OUTPUT_CSV.read_bytes()).hexdigest()

    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "endpoint": "DRD2 (D(2) dopamine receptor) binding affinity, continuous regression target",
        "endpoint_definition": (
            "pki = 9 - log10(aggregated Ki in nM), i.e. -log10(Ki in molar). Higher pki means "
            "stronger predicted binding. No binarisation threshold is applied -- unlike hERG/CYP3A4, "
            "this is a true continuous regression target, needed for a scientifically direction-correct "
            "selectivity comparison against HRH1 (see docs/psychiatric-pipeline/scientific-foundation.md)."
        ),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_manifest": {
            "path": str(RAW_MANIFEST.relative_to(ROOT)),
            "output_sha256": raw_manifest["output_sha256"],
            "retrieval_date": raw_manifest["retrieval_date"],
        },
        "filtering_rules": [
            "standard_relation == '=' only (censored '>','<','~','>=','<=' excluded)",
            f"data_validity_comment not in {sorted(_BAD_VALIDITY_FLAGS)}",
            "standard_value > 0 (required for the log-transform to pKi)",
            "structures standardised via drugsim_chem.process_structure; StructureError -> quarantined",
            "flagged mixtures excluded (no single well-defined structure)",
            "measurements grouped by standardised inchikey_full (merges salt forms of the same entity)",
            "discordant entities (>10x Ki spread, drugsim_quality.aggregation) excluded from training",
        ],
        "aggregation_method": "geometric_mean (drugsim_quality.aggregation.aggregate_continuous, is_potency=True)",
        "quarantine_count": len(quarantined),
        "quarantine_examples": quarantined[:10],
        "mixtures_excluded_count": len(mixtures_excluded),
        "discordant_entities_excluded_count": discordant_count,
        "final_compound_count": len(dataset_rows),
        "pki_distribution": {
            "min": round(min(pki_values), 4) if pki_values else None,
            "max": round(max(pki_values), 4) if pki_values else None,
            "mean": round(sum(pki_values) / len(pki_values), 4) if pki_values else None,
        },
        "output_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "output_sha256": checksum,
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(dataset_rows)} compounds to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
