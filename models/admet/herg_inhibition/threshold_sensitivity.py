#!/usr/bin/env python3
"""Phase 3.5 audit: sensitivity of the hERG blocker threshold.

Re-labels the SAME 9,589-compound dataset and SAME precomputed features at
four literature-plausible thresholds (1, 3, 10, 30 uM), retrains the exact
Random Forest config from train_manifest.json at each, and reports class
distribution, scaffold distribution, and validation+test performance.

This does not retrain the project or change the registered model -- it is a
read-only sensitivity study. The registered v0.1.0 model and its 10 uM
threshold are unchanged; see phase3.5-scientific-audit.md for the
recommendation this produces.

Usage:
    python models/admet/herg_inhibition/threshold_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[3]
DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "threshold_sensitivity_report.json"

THRESHOLDS_UM = [1, 3, 10, 30]
TRAIN_GROUPS = list(range(7))
VALIDATION_GROUP = 8
TEST_GROUP = 9


def main() -> int:
    """Relabel at each threshold, retrain, and compare."""
    df = pd.read_csv(DATASET_CSV)
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    groups = data["split_groups"]
    x_all = np.concatenate([data["descriptors"], data["fingerprints"]], axis=1)
    ic50_nm = df["aggregated_ic50_nm"].to_numpy()
    scaffolds = df["bemis_murcko_scaffold"].fillna(df["standardized_smiles"]).to_numpy()

    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    params = train_manifest["hyperparameters"]
    seed = train_manifest["random_seed"]

    train_mask = np.isin(groups, TRAIN_GROUPS)
    val_mask = groups == VALIDATION_GROUP
    test_mask = groups == TEST_GROUP

    original_labels = df["label"].to_numpy()  # the registered 10 uM labels
    results = {}

    for threshold_um in THRESHOLDS_UM:
        threshold_nm = threshold_um * 1000
        labels = (ic50_nm <= threshold_nm).astype(int)

        n_pos = int(labels.sum())
        n_neg = int(len(labels) - n_pos)

        changed_vs_10um = int((labels != original_labels).sum()) if threshold_um != 10 else 0

        # scaffold distribution: distinct scaffolds per class
        pos_scaffolds = set(scaffolds[labels == 1])
        neg_scaffolds = set(scaffolds[labels == 0])

        model = RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            class_weight="balanced",
            random_state=seed,
            n_jobs=-1,
        )
        model.fit(x_all[train_mask], labels[train_mask])

        val_prob = model.predict_proba(x_all[val_mask])[:, 1]
        val_pred = (val_prob >= 0.5).astype(int)
        test_prob = model.predict_proba(x_all[test_mask])[:, 1]
        test_pred = (test_prob >= 0.5).astype(int)

        results[f"{threshold_um}uM"] = {
            "threshold_nm": threshold_nm,
            "class_distribution": {
                "positive_blocker": n_pos,
                "negative_non_blocker": n_neg,
                "positive_fraction": round(n_pos / len(labels), 4),
            },
            "n_compounds_changed_class_vs_10uM": changed_vs_10um,
            "scaffold_distribution": {
                "distinct_scaffolds_positive_class": len(pos_scaffolds),
                "distinct_scaffolds_negative_class": len(neg_scaffolds),
                "scaffolds_in_both_classes": len(pos_scaffolds & neg_scaffolds),
            },
            "validation_performance": {
                "n": int(val_mask.sum()),
                "roc_auc": round(float(roc_auc_score(labels[val_mask], val_prob)), 4),
                "average_precision": round(float(average_precision_score(labels[val_mask], val_prob)), 4),
                "balanced_accuracy": round(float(balanced_accuracy_score(labels[val_mask], val_pred)), 4),
            },
            "test_performance": {
                "n": int(test_mask.sum()),
                "roc_auc": round(float(roc_auc_score(labels[test_mask], test_prob)), 4),
                "average_precision": round(float(average_precision_score(labels[test_mask], test_prob)), 4),
                "balanced_accuracy": round(float(balanced_accuracy_score(labels[test_mask], test_pred)), 4),
            },
        }
        print(
            f"{threshold_um} uM: pos={n_pos} ({n_pos/len(labels):.1%}) "
            f"val_auc={results[f'{threshold_um}uM']['validation_performance']['roc_auc']} "
            f"test_auc={results[f'{threshold_um}uM']['test_performance']['roc_auc']} "
            f"changed_vs_10uM={changed_vs_10um}",
            file=sys.stderr,
        )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": (
            "Read-only sensitivity study. Registered model v0.1.0 and its 10 uM threshold "
            "are unchanged by this script -- see phase3.5-scientific-audit.md for the recommendation."
        ),
        "algorithm": train_manifest["algorithm"],
        "hyperparameters": params,
        "random_seed": seed,
        "thresholds": results,
    }
    OUTPUT_JSON.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
