#!/usr/bin/env python3
"""Build the BBB permeability training dataset from the raw TDC pull.

Unlike every ChEMBL-sourced endpoint in this repository, BBB_Martins is
already a binary label at the source -- no continuous-value aggregation
or threshold binarization is needed. Standardization, salt-form
merging, and quarantine still follow this repository's established
discipline (reusing drugsim_chem.process_structure, "quarantine, never
silently drop"). Where multiple raw rows resolve to the same
standardized entity with DISAGREEING labels, the entity is excluded as
discordant -- the binary-label analogue of aggregate_continuous's
>10x-spread discordance exclusion used for every continuous endpoint.

Usage:
    python models/psychiatric/bbb_permeability/build_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from drugsim_chem import process_structure  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402
from drugsim_core.ids import generate_ulid  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RAW_CSV = ROOT / "datasets" / "raw" / "tdc_bbb_martins_raw.csv"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "tdc_bbb_martins_manifest.json"
OUTPUT_CSV = ROOT / "datasets" / "processed" / "bbb_permeability_dataset.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "processed" / "bbb_permeability_dataset_manifest.json"

DATASET_ID = "bbb_permeability"
DATASET_VERSION = "v1"


def main() -> int:
    """Run the full dataset-build pipeline and write outputs."""
    raw_manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    print(f"loaded {len(rows)} raw records", file=sys.stderr)

    quarantined: list[tuple[str, str, str]] = []
    mixtures_excluded: list[str] = []
    by_entity: dict[str, dict[str, Any]] = {}

    for i, r in enumerate(rows, 1):
        if i % 500 == 0:
            print(f"  standardised {i}/{len(rows)} molecules", file=sys.stderr)
        smiles = r["smiles"]
        try:
            processed = process_structure(smiles)
        except StructureError as exc:
            quarantined.append((r["drug_id"], smiles, str(exc)))
            continue

        if processed.is_mixture:
            mixtures_excluded.append(r["drug_id"])
            continue

        ik = processed.identity.inchikey_full
        entity = by_entity.setdefault(
            ik,
            {"processed": processed, "labels": [], "drug_ids": set()},
        )
        entity["labels"].append(int(r["bbb_label"]))
        entity["drug_ids"].add(r["drug_id"])

    print(
        f"resolved {len(rows)} raw records to {len(by_entity)} standardised entities "
        f"({len(quarantined)} quarantined, {len(mixtures_excluded)} mixtures excluded)",
        file=sys.stderr,
    )

    dataset_rows = []
    discordant_count = 0
    for ik, entity in by_entity.items():
        labels = set(entity["labels"])
        if len(labels) > 1:
            discordant_count += 1
            continue
        label = entity["labels"][0]
        processed = entity["processed"]
        dataset_rows.append(
            {
                "local_compound_id": generate_ulid(),
                "inchikey_full": ik,
                "canonical_smiles": processed.identity.canonical_smiles,
                "standardized_smiles": processed.standardized_smiles,
                "bemis_murcko_scaffold": processed.identity.bemis_murcko_scaffold or "",
                "molecular_formula": processed.identity.molecular_formula,
                "n_source_records": len(entity["labels"]),
                "label": label,
                "source_drug_ids": ";".join(sorted(entity["drug_ids"])),
            }
        )

    dataset_rows.sort(key=lambda r: r["inchikey_full"])

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dataset_rows[0].keys()) if dataset_rows else []
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset_rows)

    n_pos = sum(r["label"] for r in dataset_rows)
    n_neg = len(dataset_rows) - n_pos
    checksum = hashlib.sha256(OUTPUT_CSV.read_bytes()).hexdigest()

    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "endpoint": "Blood-brain-barrier permeability, binary classification (BBB+/BBB-)",
        "endpoint_definition": (
            "label=1 (BBB-permeant) / label=0 (BBB-non-permeant), as published by Martins et al. "
            "2012 (already a binary label at the source, no threshold or aggregation choice made "
            "in this pipeline). Passive/measured brain-plasma partitioning as a binary call, not a "
            "continuous exposure value -- see scientific-foundation.md's BBB-lipophilicity section "
            "for why 'higher LogP -> better BBB' is a SIMPLIFIED claim this label does not encode."
        ),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_manifest": {
            "path": str(RAW_MANIFEST.relative_to(ROOT)),
            "output_sha256": raw_manifest["output_sha256"],
            "retrieval_date": raw_manifest["retrieval_date"],
        },
        "filtering_rules": [
            "structures standardised via drugsim_chem.process_structure; StructureError -> quarantined",
            "flagged mixtures excluded (no single well-defined structure)",
            "raw records grouped by standardised inchikey_full (merges duplicate/salt-form entries)",
            "entities where merged records DISAGREE on the binary label excluded as discordant "
            "(binary-label analogue of the continuous->10x-spread discordance exclusion used for "
            "every ChEMBL-sourced endpoint in this repository)",
        ],
        "quarantine_count": len(quarantined),
        "quarantine_examples": quarantined[:10],
        "mixtures_excluded_count": len(mixtures_excluded),
        "discordant_entities_excluded_count": discordant_count,
        "final_compound_count": len(dataset_rows),
        "label_distribution": {
            "bbb_permeant_label_1": n_pos,
            "bbb_non_permeant_label_0": n_neg,
            "positive_fraction": round(n_pos / len(dataset_rows), 4) if dataset_rows else None,
        },
        "output_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "output_sha256": checksum,
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(dataset_rows)} compounds ({n_pos} BBB+, {n_neg} BBB-) to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
