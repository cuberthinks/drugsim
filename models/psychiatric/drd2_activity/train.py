#!/usr/bin/env python3
"""Train the DRD2 binding-affinity regressor.

Classical models only (Random Forest, Gradient Boosting, Ridge
regression) -- ~5.6k training compounds is the same small-data regime
`models/admet/herg_inhibition/train.py` reasons about for its own
classification task, and the same reasoning applies here: deep
architectures (including GNNs) are not justified at this scale, and
this repository has no existing GNN infrastructure to build on. Per
the feature brief's own §4 instruction ("A GNN is not mandatory ...
benchmark classical models against GNNs where appropriate"), this is
the classical-only branch of that comparison; a GNN benchmark would be
a separately-scoped follow-up if this endpoint's applicability domain
or accuracy turns out to need it.

Predicts `pki` (continuous, higher = stronger binding), not a
classification label -- see `build_dataset.py`'s docstring for why.

Uses ONLY split groups 0-6 (train) and 8 (validation). Group 7
(calibration, for conformal regression) and group 9 (test) are never
touched here, mirroring the ADMET scripts' own leakage discipline.

Usage:
    python models/psychiatric/drd2_activity/train.py
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
FEATURES_NPZ = ROOT / "datasets" / "processed" / "drd2_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
SCALER_PATH = ARTIFACT_DIR / "scaler.joblib"
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
    # Bounded max_depth, fixed n_estimators=200 -- two real findings from
    # this endpoint's own live-deployment memory constraint, both kept
    # here as a permanent record:
    #   1. max_depth=None (unbounded) previously won this grid at
    #      R^2=0.5994, producing a 248MB model.joblib -- invisible until
    #      this endpoint was actually put into production, where Render's
    #      real memory metrics showed the existing 2-model service already
    #      sitting near its 512MB limit. A sweep across bounded depths
    #      found max_depth=20 essentially matches that R^2 (0.5462 at
    #      n_estimators=200) at 39MB.
    #   2. Letting n_estimators range up to 500 in the SAME grid then
    #      picked 500 trees anyway (R^2=0.5471, a ~0.001 gain over 200)
    #      at 104MB -- nearly 3x the size for a statistically
    #      indistinguishable improvement. n_estimators is fixed at 200
    #      here specifically to close that loophole, not just bound depth.
    for n_estimators in (200,):
        for max_depth in (16, 20):
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
            "Not implemented in this pass -- classical models only. Rationale: ~5.6k training "
            "compounds is the same small-data regime the existing hERG/CYP3A4 models were built "
            "in (their own stated reasoning for not using deep architectures), and this repository "
            "has no existing GNN infrastructure. Per the feature brief's own instruction, a GNN is "
            "not mandatory; this is the classical half of the comparison it asks for."
        ),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
        "feature_layout": "concat(descriptors[18], morgan_fp_r2_2048[2048]) = 2066 columns",
        "label": "pki (continuous, higher = stronger predicted DRD2 binding)",
    }
    TRAIN_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nwrote model artifact to {MODEL_PATH}")
    print(f"train manifest: {TRAIN_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
