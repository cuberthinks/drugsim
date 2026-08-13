#!/usr/bin/env python3
"""Phase 9 Sec 6: baseline models, established BEFORE the primary model.

Three baselines, in increasing order of sophistication:
    1. Majority-class baseline -- always predicts the majority label.
    2. Descriptor-only logistic regression -- the 18 physicochemical
       descriptors alone, no fingerprint, no ensemble.
    3. Descriptor-only Random Forest -- same features as (2), simple
       classical ML, still no fingerprint.

The primary model (train.py) uses descriptors + Morgan fingerprint
together with a tuned Random Forest; it must beat all three of these on
the SAME validation group (group 8) to be a justified choice, not merely
the model with the single highest metric in isolation.

Usage:
    python models/admet/cyp3a4_inhibition/baselines.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
OUTPUT_JSON = Path(__file__).resolve().parent / "baselines_report.json"

RANDOM_SEED = 42
TRAIN_GROUPS = list(range(7))
VALIDATION_GROUP = 8


def _load(data: dict, groups: list[int], descriptors_only: bool = False) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    if descriptors_only:
        x = data["descriptors"][mask]
    else:
        x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


def _metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    y_pred = (y_prob >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "average_precision": round(float(average_precision_score(y_true, y_prob)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
    }


def main() -> int:
    data = np.load(FEATURES_NPZ, allow_pickle=True)

    x_train_desc, y_train = _load(data, TRAIN_GROUPS, descriptors_only=True)
    x_val_desc, y_val = _load(data, [VALIDATION_GROUP], descriptors_only=True)
    print(f"train: {len(y_train)} ({y_train.mean():.1%} positive), validation: {len(y_val)} ({y_val.mean():.1%} positive)", file=sys.stderr)

    results = {}

    # --- 1. Majority-class baseline ---
    dummy = DummyClassifier(strategy="most_frequent", random_state=RANDOM_SEED)
    dummy.fit(x_train_desc, y_train)
    dummy_prob = dummy.predict_proba(x_val_desc)[:, 1]
    # A constant-probability predictor has an undefined/degenerate ROC-AUC
    # (no threshold varies the decision) -- report accuracy honestly
    # instead of a misleading 0.5 placeholder.
    results["majority_class"] = {
        "description": "Always predicts the majority training label.",
        "predicted_label": int(dummy.predict(x_val_desc)[0]),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_val, dummy.predict(x_val_desc))), 4),
        "roc_auc": None,
        "note": "ROC-AUC is undefined for a constant predictor (ties every ranking) -- not reported as a number.",
    }

    # --- 2. Descriptor-only logistic regression ---
    scaler = StandardScaler().fit(x_train_desc)
    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED)
    lr.fit(scaler.transform(x_train_desc), y_train)
    lr_prob = lr.predict_proba(scaler.transform(x_val_desc))[:, 1]
    results["descriptor_only_logistic_regression"] = {
        "description": "18 physicochemical descriptors only, no fingerprint, linear model.",
        **_metrics(y_val, lr_prob),
    }

    # --- 3. Descriptor-only Random Forest ---
    rf_desc = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
    rf_desc.fit(x_train_desc, y_train)
    rf_desc_prob = rf_desc.predict_proba(x_val_desc)[:, 1]
    results["descriptor_only_random_forest"] = {
        "description": "18 physicochemical descriptors only, no fingerprint, simple RF (n_estimators=300, default depth).",
        **_metrics(y_val, rf_desc_prob),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluated_on": "validation group 8 (never the held-out test group 9)",
        "n_train": int(len(y_train)),
        "n_validation": int(len(y_val)),
        "baselines": results,
        "purpose": (
            "The primary model (train.py, descriptors+fingerprint, tuned Random "
            "Forest) must be compared against these three numbers, not evaluated "
            "in isolation -- see train_manifest.json's baseline_comparison field."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
