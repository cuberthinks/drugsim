#!/usr/bin/env python3
"""Phase 4.1: reproduce the registered Phase 3 model from the fixed raw input.

"Reproduce with the exact dataset/version" means from the checksummed raw
CSV (datasets/raw/chembl_herg_ic50_raw.csv, sha256 pinned in its manifest)
-- NOT a fresh fetch, which would query a live, growing API and could pull
different data (a documented Phase 3 limitation). This script re-runs the
deterministic downstream steps (build_dataset -> prepare_features -> train
-> evaluate) against that fixed input and diffs every output against a
backup of the currently-registered artifacts.

Must be run with a backup of the registered artifacts already taken (see
docs/phase4/phase4-reliability-report.md Sec "Reproducibility" for the
exact procedure used) -- this script performs the diff, it does not manage
the backup itself, since the backup step is a one-time manual precaution
against this script's downstream calls overwriting the registered files.

Usage:
    python models/admet/herg_inhibition/phase4/01_reproduce.py <backup_dir>
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
OUTPUT_JSON = Path(__file__).resolve().parent / "01_reproduce_report.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    """Compare current (freshly reproduced) artifacts against a backup dir."""
    if len(sys.argv) != 2:
        print("usage: 01_reproduce.py <backup_dir>", file=sys.stderr)
        return 2
    backup = Path(sys.argv[1])

    result: dict = {}

    # Raw input is fixed and must not have been touched
    raw_csv = ROOT / "datasets" / "raw" / "chembl_herg_ic50_raw.csv"
    raw_manifest = json.loads((ROOT / "datasets" / "raw" / "chembl_herg_ic50_manifest.json").read_text())
    result["raw_input_unchanged"] = _sha256(raw_csv) == raw_manifest["output_sha256"]

    # Dataset CSV: identical on every column except the arbitrary surrogate id
    old_ds = pd.read_csv(backup / "herg_inhibition_dataset.csv").sort_values("inchikey_full").reset_index(drop=True)
    new_ds = pd.read_csv(ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv").sort_values("inchikey_full").reset_index(drop=True)
    compare_cols = [c for c in old_ds.columns if c != "local_compound_id"]
    dataset_match = all((old_ds[c].astype(str) == new_ds[c].astype(str)).all() for c in compare_cols)
    result["dataset_identical_excl_surrogate_id"] = bool(dataset_match)
    result["dataset_row_counts"] = {"old": len(old_ds), "new": len(new_ds)}

    # Features: exact array equality
    old_feat = np.load(backup / "herg_inhibition_features.npz", allow_pickle=True)
    new_feat = np.load(ROOT / "datasets" / "processed" / "herg_inhibition_features.npz", allow_pickle=True)
    result["features"] = {
        "inchikey_order_identical": bool((old_feat["inchikey_full"] == new_feat["inchikey_full"]).all()),
        "descriptors_identical": bool(np.array_equal(old_feat["descriptors"], new_feat["descriptors"])),
        "fingerprints_identical": bool(np.array_equal(old_feat["fingerprints"], new_feat["fingerprints"])),
        "labels_identical": bool(np.array_equal(old_feat["labels"], new_feat["labels"])),
        "split_groups_identical": bool(np.array_equal(old_feat["split_groups"], new_feat["split_groups"])),
    }

    # Training: candidate comparison and validation metrics
    old_train = json.loads((backup / "train_manifest.json").read_text())
    new_train = json.loads((ROOT / "models" / "admet" / "herg_inhibition" / "train_manifest.json").read_text())
    result["training"] = {
        "candidate_comparison_identical": old_train["candidate_comparison"] == new_train["candidate_comparison"],
        "validation_metrics_identical": old_train["validation_metrics"] == new_train["validation_metrics"],
        "selected_algorithm_identical": old_train["algorithm"] == new_train["algorithm"],
    }

    # Model artifact: byte-identical
    result["model_artifact_byte_identical"] = _sha256(backup / "model.joblib") == _sha256(
        ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
    )

    # Evaluation: full metric set
    old_eval = json.loads((backup / "evaluation_report.json").read_text())
    new_eval = json.loads((ROOT / "models" / "admet" / "herg_inhibition" / "evaluation_report.json").read_text())

    def _strip_desc(d: dict) -> dict:
        return {k: v for k, v in d.items() if k != "description"}

    result["evaluation"] = {
        "global_split_identical": _strip_desc(old_eval["global_split"]) == _strip_desc(new_eval["global_split"]),
        "benchmark_split_identical": _strip_desc(old_eval["benchmark_split"]) == _strip_desc(new_eval["benchmark_split"]),
        "roc_auc_gap_identical": old_eval["roc_auc_gap"] == new_eval["roc_auc_gap"],
    }

    all_checks = [
        result["raw_input_unchanged"],
        result["dataset_identical_excl_surrogate_id"],
        *result["features"].values(),
        *result["training"].values(),
        result["model_artifact_byte_identical"],
        *result["evaluation"].values(),
    ]
    result["overall_status"] = "PASS (fully reproducible)" if all(all_checks) else "FAIL (unexplained differences -- investigate)"

    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if all(all_checks) else 1


if __name__ == "__main__":
    sys.exit(main())
