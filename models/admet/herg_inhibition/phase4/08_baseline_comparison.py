#!/usr/bin/env python3
"""Phase 4.8: baseline comparison on the internal held-out test set.

Majority-class, random (stratified by train prevalence), and a genuinely
simple descriptor baseline (LogP + MW + TPSA only -- three classic,
textbook hERG-liability-associated properties, not the full 18-descriptor
set Phase 4.3 already evaluated as "descriptors-only") against the
registered Random Forest.

Usage:
    python models/admet/herg_inhibition/phase4/08_baseline_comparison.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
OUTPUT_JSON = Path(__file__).resolve().parent / "08_baseline_comparison_report.json"

TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9
RANDOM_SEED = 42
# indices into DESCRIPTOR_FIELDS (prepare_features.py order) for LogP, MW, TPSA
SIMPLE_DESCRIPTOR_IDX = {"mw_g_mol": 0, "logp_crippen": 2, "tpsa_a2": 4}


def main() -> int:
    """Compare the registered model against majority/random/simple baselines."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    test_mask = data["split_groups"] == TEST_GROUP
    y_train, y_test = data["labels"][train_mask], data["labels"][test_mask]

    train_prevalence = float(y_train.mean())
    majority_class = int(round(train_prevalence))

    # --- Majority-class baseline ---
    majority_pred = np.full(len(y_test), majority_class)
    majority_acc = float((majority_pred == y_test).mean())
    majority_bal_acc = float(balanced_accuracy_score(y_test, majority_pred))

    # --- Random baseline (stratified by train prevalence, averaged over repeats) ---
    rng = np.random.default_rng(RANDOM_SEED)
    random_accs, random_bal_accs, random_aucs = [], [], []
    for _ in range(20):
        random_pred = (rng.random(len(y_test)) < train_prevalence).astype(int)
        random_prob = np.full(len(y_test), train_prevalence)
        random_accs.append((random_pred == y_test).mean())
        random_bal_accs.append(balanced_accuracy_score(y_test, random_pred))
        random_aucs.append(0.5)  # a constant/random-noise score has no discriminative ranking by construction
    random_acc = float(np.mean(random_accs))
    random_bal_acc = float(np.mean(random_bal_accs))

    # --- Simple descriptor baseline: LogP + MW + TPSA only ---
    idx = list(SIMPLE_DESCRIPTOR_IDX.values())
    x_train_simple = data["descriptors"][train_mask][:, idx]
    x_test_simple = data["descriptors"][test_mask][:, idx]
    simple_model = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED)
    simple_model.fit(x_train_simple, y_train)
    simple_prob = simple_model.predict_proba(x_test_simple)[:, 1]
    simple_pred = (simple_prob >= 0.5).astype(int)

    # --- Registered model ---
    model = joblib.load(MODEL_PATH)
    x_test_full = np.concatenate([data["descriptors"][test_mask], data["fingerprints"][test_mask]], axis=1)
    reg_prob = model.predict_proba(x_test_full)[:, 1]
    reg_pred = (reg_prob >= 0.5).astype(int)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_set_n": int(test_mask.sum()),
        "test_set_positive_fraction": round(float(y_test.mean()), 4),
        "train_prevalence_used_for_majority_and_random": round(train_prevalence, 4),
        "baselines": {
            "majority_class": {
                "predicts": "blocker" if majority_class == 1 else "non_blocker",
                "accuracy": round(majority_acc, 4),
                "balanced_accuracy": round(majority_bal_acc, 4),
                "roc_auc": None,
                "note": "undefined ROC-AUC -- a constant prediction has no ranking",
            },
            "random_stratified": {
                "accuracy": round(random_acc, 4),
                "balanced_accuracy": round(random_bal_acc, 4),
                "roc_auc": 0.5,
                "note": "20-repeat average, predictions drawn at the train-set positive rate",
            },
            "simple_descriptor_logp_mw_tpsa": {
                "accuracy": round(float((simple_pred == y_test).mean()), 4),
                "balanced_accuracy": round(float(balanced_accuracy_score(y_test, simple_pred)), 4),
                "roc_auc": round(float(roc_auc_score(y_test, simple_prob)), 4),
                "n_features": 3,
            },
        },
        "registered_model": {
            "accuracy": round(float((reg_pred == y_test).mean()), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_test, reg_pred)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, reg_prob)), 4),
            "n_features": x_test_full.shape[1],
        },
    }
    improvement_over_majority = result["registered_model"]["balanced_accuracy"] - majority_bal_acc
    improvement_over_simple = result["registered_model"]["roc_auc"] - result["baselines"]["simple_descriptor_logp_mw_tpsa"]["roc_auc"]
    result["improvement"] = {
        "balanced_accuracy_over_majority_class": round(improvement_over_majority, 4),
        "roc_auc_over_simple_descriptor_baseline": round(improvement_over_simple, 4),
    }

    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
