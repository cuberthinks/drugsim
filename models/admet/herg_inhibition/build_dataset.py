#!/usr/bin/env python3
"""Build the hERG inhibition training dataset from the raw ChEMBL pull.

Reuses Phase 2 code directly rather than reimplementing chemistry or
aggregation logic:
    * drugsim_chem.process_structure  -- parsing, standardisation, identity
    * drugsim_quality.aggregation.aggregate_continuous -- discordance-aware
      potency aggregation (geometric mean; >10x spread is discordant and
      excluded, never averaged over silently)

Pipeline (see docs/phase3/phase3-model-validation-report.md for the
rationale behind each rule):
    1. Load the raw CSV (models/admet/herg_inhibition/fetch_chembl_data.py).
    2. Keep only uncensored measurements (standard_relation == '=') and drop
       records ChEMBL itself flags as a transcription/author error --
       matches the TDS training-set-selection rule (value_relation = '=')
       and Phase 1's "do not silently coerce censored data" rule.
    3. Standardise every distinct SMILES via the real drugsim_chem pipeline;
       invalid structures are quarantined (recorded, not dropped silently).
    4. Group raw measurements by the STANDARDISED entity (inchikey_full),
       not by ChEMBL molecule id -- this merges different salt forms of the
       same active entity onto one set of measurements before aggregating,
       which is the scientifically correct behaviour for potency (a salt
       form and its free base block the same channel) even though it means
       two distinct compound records can never be distinguished downstream
       (a known, documented limitation of the current identity pipeline --
       see docs/phase2/phase2-completion-report.md Sec 5).
    5. Aggregate each entity's measurements with aggregate_continuous;
       exclude discordant entities (>10x spread) from training entirely.
    6. Exclude flagged mixtures (no well-defined single structure).
    7. Binarise at a documented threshold into the training label.

Usage:
    python models/admet/herg_inhibition/build_dataset.py
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
from drugsim_quality.aggregation import aggregate_continuous  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
RAW_CSV = ROOT / "datasets" / "raw" / "chembl_herg_ic50_raw.csv"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "chembl_herg_ic50_manifest.json"
OUTPUT_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "processed" / "herg_inhibition_dataset_manifest.json"

DATASET_ID = "herg_inhibition"
DATASET_VERSION = "v1"

#: Records ChEMBL itself flags as unreliable -- excluded, not down-weighted.
_BAD_VALIDITY_FLAGS = {"Potential transcription error", "Potential author error"}

#: hERG-blocker cutoff. 10 uM (10,000 nM) is a widely used convention in the
#: published QSAR literature for a binary hERG liability call (see e.g.
#: Doddareddy et al. 2010, Bioorg Med Chem; many hERG classification studies
#: use thresholds in the 1-30 uM range) -- a convention, not a universal
#: constant, and recorded here as exactly that.
BLOCKER_THRESHOLD_NM = 10_000.0


def _load_filtered_raw_rows() -> list[dict[str, Any]]:
    with RAW_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    kept = [
        r
        for r in rows
        if r["standard_relation"] == "="
        and r["data_validity_comment"] not in _BAD_VALIDITY_FLAGS
        and r["standard_value"]
    ]
    return kept


def main() -> int:
    """Run the full dataset-build pipeline and write outputs."""
    raw_manifest = json.loads(RAW_MANIFEST.read_text(encoding="utf-8"))
    rows = _load_filtered_raw_rows()
    print(f"loaded {len(rows)} uncensored, non-error-flagged raw records", file=sys.stderr)

    # Standardise each distinct ChEMBL molecule id's SMILES exactly once.
    by_molecule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_molecule[r["molecule_chembl_id"]].append(r)

    quarantined: list[tuple[str, str, str]] = []
    mixtures_excluded: list[str] = []
    # inchikey_full -> accumulated state
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
        label = 1 if agg.aggregated_value <= BLOCKER_THRESHOLD_NM else 0
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
                "aggregated_ic50_nm": round(agg.aggregated_value, 4),
                "value_spread_log10": agg.value_spread_log10,
                "label": label,
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

    n_pos = sum(r["label"] for r in dataset_rows)
    n_neg = len(dataset_rows) - n_pos
    checksum = hashlib.sha256(OUTPUT_CSV.read_bytes()).hexdigest()

    manifest = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "endpoint": "hERG (KCNH2/Kv11.1) inhibition, binary blocker classification",
        "endpoint_definition": (
            f"label=1 (blocker) if aggregated IC50 <= {BLOCKER_THRESHOLD_NM:.0f} nM "
            f"({BLOCKER_THRESHOLD_NM / 1000:.0f} uM), else label=0 (non-blocker). "
            "Threshold is a literature convention (commonly 1-30 uM across "
            "published hERG QSAR studies), not a universal biological constant."
        ),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_manifest": {
            "path": str(RAW_MANIFEST.relative_to(ROOT)),
            "output_sha256": raw_manifest["output_sha256"],
            "retrieval_date": raw_manifest["retrieval_date"],
        },
        "filtering_rules": [
            "standard_relation == '=' only (censored '>','<','~','>=','<=' excluded per TDS Sec 6.3.1)",
            f"data_validity_comment not in {sorted(_BAD_VALIDITY_FLAGS)}",
            "structures standardised via drugsim_chem.process_structure; StructureError -> quarantined",
            "flagged mixtures excluded (no single well-defined structure)",
            "measurements grouped by standardised inchikey_full (merges salt forms of the same entity)",
            "discordant entities (>10x IC50 spread, drugsim_quality.aggregation) excluded from training",
        ],
        "aggregation_method": "geometric_mean (drugsim_quality.aggregation.aggregate_continuous, is_potency=True)",
        "quarantine_count": len(quarantined),
        "quarantine_examples": quarantined[:10],
        "mixtures_excluded_count": len(mixtures_excluded),
        "discordant_entities_excluded_count": discordant_count,
        "final_compound_count": len(dataset_rows),
        "label_distribution": {
            "blocker_label_1": n_pos,
            "non_blocker_label_0": n_neg,
            "positive_fraction": round(n_pos / len(dataset_rows), 4) if dataset_rows else None,
        },
        "output_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "output_sha256": checksum,
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(dataset_rows)} compounds ({n_pos} blocker, {n_neg} non-blocker) to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
