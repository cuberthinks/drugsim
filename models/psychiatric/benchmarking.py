#!/usr/bin/env python3
"""Step 10: benchmark every new psychiatric-pipeline endpoint against real baselines.

DRD2/HRH1/CYP2D6/BBB's own train.py scripts already compare three
candidate algorithms against EACH OTHER (RF/GBM/LogReg or RF/GBM/Ridge)
on the validation group, but none of them compare the champion against
a baseline that would reveal whether the fingerprint is doing any real
work -- `models/admet/cyp3a4_inhibition/baselines.py` already
established this rigor (majority-class + descriptor-only baselines) for
CYP3A4; this script applies the identical methodology to the four new
endpoints in one place, computed fresh on each endpoint's own real
test set (never estimated or assumed).

Classification endpoints (CYP2D6, BBB): majority-class baseline
(always predicts the training-set's most frequent label) and a
descriptor-only (no fingerprint) RandomForestClassifier, both scored on
the SAME held-out test group the champion model was evaluated on.

Regression endpoints (DRD2, HRH1): a predict-the-training-mean baseline
(R^2 = 0 by construction -- included for completeness, not because it
is informative) and a descriptor-only RandomForestRegressor, same test
group.

Usage:
    python models/psychiatric/benchmarking.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import balanced_accuracy_score, r2_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_JSON = Path(__file__).resolve().parent / "benchmarking_report.json"

RANDOM_SEED = 42
TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9

CLASSIFICATION_ENDPOINTS = ["cyp2d6_activity", "bbb_permeability"]
REGRESSION_ENDPOINTS = ["drd2", "hrh1"]


def _load(features_path: Path, groups: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    data = np.load(features_path, allow_pickle=True)
    mask = np.isin(data["split_groups"], groups)
    descriptors = data["descriptors"][mask]
    x = np.concatenate([descriptors, data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, descriptors, y


def _benchmark_classification(endpoint_dir: str) -> dict:
    features_path = ROOT / "datasets" / "processed" / f"{endpoint_dir}_features.npz"
    model_path = ROOT / "models" / "psychiatric" / endpoint_dir / "artifact" / "model.joblib"
    x_train, desc_train, y_train = _load(features_path, TRAIN_GROUPS)
    x_test, desc_test, y_test = _load(features_path, [TEST_GROUP])

    champion = joblib.load(model_path)
    champion_prob = champion.predict_proba(x_test)[:, 1]
    champion_roc_auc = round(float(roc_auc_score(y_test, champion_prob)), 4)

    majority = DummyClassifier(strategy="most_frequent", random_state=RANDOM_SEED).fit(x_train, y_train)
    majority_pred = majority.predict(x_test)
    majority_balanced_accuracy = round(float(balanced_accuracy_score(y_test, majority_pred)), 4)

    desc_only = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
    desc_only.fit(desc_train, y_train)
    desc_only_roc_auc = round(float(roc_auc_score(y_test, desc_only.predict_proba(desc_test)[:, 1])), 4)

    return {
        "task_type": "classification",
        "n_test": int(len(y_test)),
        "champion_roc_auc": champion_roc_auc,
        "majority_class_balanced_accuracy": majority_balanced_accuracy,
        "majority_class_roc_auc": 0.5,
        "descriptor_only_random_forest_roc_auc": desc_only_roc_auc,
        "improvement_over_descriptor_only_roc_auc": round(champion_roc_auc - desc_only_roc_auc, 4),
        "fingerprint_adds_real_signal": champion_roc_auc > desc_only_roc_auc,
        "meaningfully_beats_majority_baseline": champion_roc_auc > 0.55,
    }


def _benchmark_regression(endpoint_dir: str) -> dict:
    features_path = ROOT / "datasets" / "processed" / f"{endpoint_dir}_activity_features.npz"
    model_path = ROOT / "models" / "psychiatric" / f"{endpoint_dir}_activity" / "artifact" / "model.joblib"
    x_train, desc_train, y_train = _load(features_path, TRAIN_GROUPS)
    x_test, desc_test, y_test = _load(features_path, [TEST_GROUP])

    champion = joblib.load(model_path)
    champion_r2 = round(float(r2_score(y_test, champion.predict(x_test))), 4)

    mean_baseline = DummyRegressor(strategy="mean").fit(x_train, y_train)
    mean_baseline_r2 = round(float(r2_score(y_test, mean_baseline.predict(x_test))), 4)

    desc_only = RandomForestRegressor(n_estimators=300, random_state=RANDOM_SEED, n_jobs=-1)
    desc_only.fit(desc_train, y_train)
    desc_only_r2 = round(float(r2_score(y_test, desc_only.predict(desc_test))), 4)

    return {
        "task_type": "regression",
        "n_test": int(len(y_test)),
        "champion_r2": champion_r2,
        "predict_mean_baseline_r2": mean_baseline_r2,
        "descriptor_only_random_forest_r2": desc_only_r2,
        "improvement_over_descriptor_only_r2": round(champion_r2 - desc_only_r2, 4),
        "fingerprint_adds_real_signal": champion_r2 > desc_only_r2,
        "meaningfully_beats_predict_mean_baseline": champion_r2 > mean_baseline_r2 + 0.05,
    }


def main() -> int:
    """Run every endpoint's benchmark and write one combined report."""
    results = {}
    for endpoint_dir in CLASSIFICATION_ENDPOINTS:
        print(f"benchmarking {endpoint_dir}...", file=sys.stderr)
        results[endpoint_dir] = _benchmark_classification(endpoint_dir)
        print(f"  {json.dumps(results[endpoint_dir])}", file=sys.stderr)

    for endpoint_dir in REGRESSION_ENDPOINTS:
        print(f"benchmarking {endpoint_dir}_activity...", file=sys.stderr)
        results[f"{endpoint_dir}_activity"] = _benchmark_regression(endpoint_dir)
        print(f"  {json.dumps(results[f'{endpoint_dir}_activity'])}", file=sys.stderr)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": (
            "Mirrors models/admet/cyp3a4_inhibition/baselines.py's methodology (majority-class + "
            "descriptor-only baselines), applied fresh to DRD2/HRH1/CYP2D6/BBB, computed on each "
            "endpoint's own real held-out test group (split_group 9) -- never estimated."
        ),
        "results": results,
        "hERG_and_CYP3A4_reference": {
            "note": (
                "Not recomputed here -- both already have their own baseline_comparison in "
                "models/admet/cyp3a4_inhibition/baselines_report.json and "
                "models/registry/herg_inhibition_v1.json. Included as context only."
            ),
        },
        "summary": {
            endpoint: {
                "fingerprint_adds_real_signal": r["fingerprint_adds_real_signal"],
            }
            for endpoint, r in results.items()
        },
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
