#!/usr/bin/env python3
"""Train the hERG inhibition baseline classifier.

Classical models only (Random Forest, Gradient Boosting, Logistic
Regression) -- ~9.6k compounds is squarely the small-data regime TDS Sec 6.1
identifies, where deep architectures are not justified. Random Forest is
selected as the primary baseline (robust with minimal tuning on mixed
descriptor+fingerprint features, handles the moderate class imbalance well
with class_weight="balanced"); Logistic Regression and Gradient Boosting are
trained too, purely for comparison, so the choice is demonstrated rather
than asserted.

Uses ONLY split groups 0-6 (train) and 8 (validation, for the light
hyperparameter search below). Group 7 (calibration) and group 9 (test) are
never touched by this script -- enforced by simply never reading them here,
not by a runtime check, so there is no path by which this script could leak
into them.

All randomness is seeded (RANDOM_SEED) for reproducibility.

Usage:
    python models/admet/herg_inhibition/train.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
SCALER_PATH = ARTIFACT_DIR / "scaler.joblib"
# Metadata, not a binary artefact -- tracked in git (unlike artifact/, which
# is gitignored) so hyperparameters/metrics/seed survive as provenance even
# though the model.joblib itself does not (Phase 1 Step 11 Sec 3: "models/
# holds code, never artefacts").
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"

RANDOM_SEED = 42
TRAIN_GROUPS = list(range(7))  # 0-6
VALIDATION_GROUP = 8


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


def main() -> int:
    """Fit the baseline model and a couple of comparison models."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    x_train, y_train = _load_split(data, TRAIN_GROUPS)
    x_val, y_val = _load_split(data, [VALIDATION_GROUP])
    print(f"train: {x_train.shape[0]} compounds ({y_train.mean():.1%} positive)", file=sys.stderr)
    print(f"validation: {x_val.shape[0]} compounds ({y_val.mean():.1%} positive)", file=sys.stderr)

    # Descriptors and fingerprint bits are on very different scales; scaling
    # only matters for Logistic Regression (RF/GBM are scale-invariant) but
    # is applied uniformly and saved alongside the model so inference always
    # uses the exact same transform as training.
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_val_scaled = scaler.transform(x_val)

    candidates = {}

    # Small, fixed hyperparameter grid for Random Forest, selected on the
    # validation group only (group 9 test is never touched here).
    best_rf, best_rf_auc, best_rf_params = None, -1.0, None
    for n_estimators in (200, 500):
        for max_depth in (None, 20):
            rf = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                class_weight="balanced",
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )
            rf.fit(x_train, y_train)
            auc = roc_auc_score(y_val, rf.predict_proba(x_val)[:, 1])
            if auc > best_rf_auc:
                best_rf, best_rf_auc, best_rf_params = rf, auc, {
                    "n_estimators": n_estimators, "max_depth": max_depth
                }
    candidates["random_forest"] = (best_rf, best_rf_auc, best_rf_params)

    gbm = GradientBoostingClassifier(random_state=RANDOM_SEED)
    gbm.fit(x_train, y_train)
    gbm_auc = roc_auc_score(y_val, gbm.predict_proba(x_val)[:, 1])
    candidates["gradient_boosting"] = (gbm, gbm_auc, gbm.get_params())

    lr = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=RANDOM_SEED)
    lr.fit(x_train_scaled, y_train)
    lr_auc = roc_auc_score(y_val, lr.predict_proba(x_val_scaled)[:, 1])
    candidates["logistic_regression"] = (lr, lr_auc, lr.get_params())

    print("\nValidation-group (group 8) ROC-AUC by candidate:", file=sys.stderr)
    for name, (_, auc, _) in candidates.items():
        print(f"  {name}: {auc:.4f}", file=sys.stderr)

    best_name = max(candidates, key=lambda k: candidates[k][1])
    best_model, best_auc, best_params = candidates[best_name]
    print(f"\nSelected: {best_name} (validation ROC-AUC {best_auc:.4f})", file=sys.stderr)

    val_probs = (
        best_model.predict_proba(x_val_scaled if best_name == "logistic_regression" else x_val)[:, 1]
    )
    val_preds = (val_probs >= 0.5).astype(int)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    manifest = {
        "algorithm": best_name,
        "hyperparameters": {k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v)) for k, v in best_params.items()},
        "random_seed": RANDOM_SEED,
        "requires_scaling": best_name == "logistic_regression",
        "train_groups": TRAIN_GROUPS,
        "validation_group": VALIDATION_GROUP,
        "n_train": int(x_train.shape[0]),
        "n_validation": int(x_val.shape[0]),
        "train_positive_fraction": round(float(y_train.mean()), 4),
        "validation_metrics": {
            "roc_auc": round(float(roc_auc_score(y_val, val_probs)), 4),
            "average_precision": round(float(average_precision_score(y_val, val_probs)), 4),
            "balanced_accuracy_at_0.5": round(float(balanced_accuracy_score(y_val, val_preds)), 4),
        },
        "candidate_comparison": {
            name: round(float(auc), 4) for name, (_, auc, _) in candidates.items()
        },
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
        "feature_layout": "concat(descriptors[18], morgan_fp_r2_2048[2048]) = 2066 columns",
    }
    TRAIN_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nwrote model artifact to {MODEL_PATH}")
    print(f"train manifest: {TRAIN_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
