#!/usr/bin/env python3
"""Train the HRH1 binding-affinity regressor.

Mirrors `models/psychiatric/drd2_activity/train.py` exactly -- same
candidates, same hyperparameter grid, same random seed, same
train/validation groups. See that file's docstring for the full
rationale (small-data regime, no GNN in this pass).

**Real caveat, worth stating up front**: this dataset (916 training
compounds) is noticeably smaller than DRD2's (5,611) -- expect wider
uncertainty and a less reliable applicability domain; see
evaluate.py's output and the final report for exactly how much smaller.

Usage:
    python models/psychiatric/hrh1_activity/train.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "hrh1_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
SCALER_PATH = ARTIFACT_DIR / "scaler.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"

RANDOM_SEED = 42
TRAIN_GROUPS = list(range(7))
VALIDATION_GROUP = 8


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


def main() -> int:
    """Fit the baseline regressor and a couple of comparison models."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    x_train, y_train = _load_split(data, TRAIN_GROUPS)
    x_val, y_val = _load_split(data, [VALIDATION_GROUP])
    print(f"train: {x_train.shape[0]} compounds, pKi mean {y_train.mean():.2f}", file=sys.stderr)
    print(f"validation: {x_val.shape[0]} compounds, pKi mean {y_val.mean():.2f}", file=sys.stderr)

    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    x_val_scaled = scaler.transform(x_val)

    candidates = {}

    best_rf, best_rf_r2, best_rf_params = None, -np.inf, None
    for n_estimators in (200, 500):
        for max_depth in (None, 20):
            rf = RandomForestRegressor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                random_state=RANDOM_SEED,
                n_jobs=-1,
            )
            rf.fit(x_train, y_train)
            r2 = r2_score(y_val, rf.predict(x_val))
            if r2 > best_rf_r2:
                best_rf, best_rf_r2, best_rf_params = rf, r2, {"n_estimators": n_estimators, "max_depth": max_depth}
    candidates["random_forest"] = (best_rf, best_rf_r2, best_rf_params)

    gbm = GradientBoostingRegressor(random_state=RANDOM_SEED)
    gbm.fit(x_train, y_train)
    gbm_r2 = r2_score(y_val, gbm.predict(x_val))
    candidates["gradient_boosting"] = (gbm, gbm_r2, gbm.get_params())

    ridge = Ridge(alpha=1.0, random_state=RANDOM_SEED)
    ridge.fit(x_train_scaled, y_train)
    ridge_r2 = r2_score(y_val, ridge.predict(x_val_scaled))
    candidates["ridge_regression"] = (ridge, ridge_r2, ridge.get_params())

    print("\nValidation-group (group 8) R^2 by candidate:", file=sys.stderr)
    for name, (_, r2, _) in candidates.items():
        print(f"  {name}: {r2:.4f}", file=sys.stderr)

    best_name = max(candidates, key=lambda k: candidates[k][1])
    best_model, best_r2, best_params = candidates[best_name]
    print(f"\nSelected: {best_name} (validation R^2 {best_r2:.4f})", file=sys.stderr)

    val_preds = best_model.predict(x_val_scaled if best_name == "ridge_regression" else x_val)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(best_model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    manifest = {
        "algorithm": best_name,
        "hyperparameters": {k: (v if isinstance(v, (int, float, str, bool, type(None))) else str(v)) for k, v in best_params.items()},
        "random_seed": RANDOM_SEED,
        "requires_scaling": best_name == "ridge_regression",
        "train_groups": TRAIN_GROUPS,
        "validation_group": VALIDATION_GROUP,
        "n_train": int(x_train.shape[0]),
        "n_validation": int(x_val.shape[0]),
        "train_pki_mean": round(float(y_train.mean()), 4),
        "validation_metrics": {
            "r2": round(float(r2_score(y_val, val_preds)), 4),
            "mae": round(float(mean_absolute_error(y_val, val_preds)), 4),
            "rmse": round(float(mean_squared_error(y_val, val_preds) ** 0.5), 4),
        },
        "candidate_comparison": {name: round(float(r2), 4) for name, (_, r2, _) in candidates.items()},
        "gnn_benchmark": (
            "Not implemented in this pass -- see drd2_activity/train_manifest.json's identical note. "
            "Even more true here: 916 training compounds is far too small for a deep architecture."
        ),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
        "feature_layout": "concat(descriptors[18], morgan_fp_r2_2048[2048]) = 2066 columns",
        "label": "pki (continuous, higher = stronger predicted HRH1 binding)",
    }
    TRAIN_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nwrote model artifact to {MODEL_PATH}")
    print(f"train manifest: {TRAIN_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
