#!/usr/bin/env python3
"""Evaluate the HRH1 regressor on the held-out test group -- touched once, here.

Mirrors `models/psychiatric/drd2_activity/evaluate.py` exactly -- same
method for global metrics, split conformal prediction intervals, and
applicability domain (with the same exclude-self correction applied
from the start this time). See that file's docstring for the full
methodology.

**Real caveat specific to this endpoint**: 1,395 total compounds (916
train / 189 calibration / 144 validation / 146 test) is small enough
that per-subgroup metrics (e.g. in-domain vs. out-of-domain R^2 on an
already-146-compound test set) can be noisy from sample size alone --
this script flags a subgroup's own size next to any of its stats rather
than reporting a number without that context.

**External validation**: not performed, same reason as DRD2 -- no
independent second-source dataset identified for HRH1 either.

Usage:
    python models/psychiatric/hrh1_activity/evaluate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "hrh1_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "evaluation_report.json"

TRAIN_GROUPS = list(range(7))
CALIBRATION_GROUP = 7
TEST_GROUP = 9
NOMINAL_CONFIDENCE = 0.90
AD_KNN_K = 5
#: Below this subgroup size, a per-subgroup R^2 is reported with an
#: explicit low-sample-size caveat rather than presented as reliable.
MIN_SUBGROUP_N_FOR_STABLE_R2 = 20


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    descriptors = data["descriptors"][mask]
    fingerprints = data["fingerprints"][mask]
    x = np.concatenate([descriptors, fingerprints], axis=1)
    y = data["labels"][mask]
    return x, fingerprints, y


def _tanimoto_max_similarity(query_fps: np.ndarray, train_fps: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    """Max Tanimoto similarity of each query fingerprint to any training fingerprint.

    `exclude_self` must be True when query_fps IS train_fps -- see
    drd2_activity/evaluate.py's identical function for the self-match
    bug this guards against.
    """
    train_fps = train_fps.astype(np.float32)
    query_fps = query_fps.astype(np.float32)
    intersection = query_fps @ train_fps.T
    query_popcount = query_fps.sum(axis=1, keepdims=True)
    train_popcount = train_fps.sum(axis=1, keepdims=True).T
    union = query_popcount + train_popcount - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        tanimoto = np.where(union > 0, intersection / union, 0.0)
    if exclude_self:
        np.fill_diagonal(tanimoto, -1.0)
    return tanimoto.max(axis=1)


def _knn_descriptor_distance(query_desc: np.ndarray, train_desc_scaled: np.ndarray, mean: np.ndarray, std: np.ndarray, k: int, exclude_self: bool = False) -> np.ndarray:
    scaled = (query_desc - mean) / np.where(std > 0, std, 1.0)
    dists = np.linalg.norm(scaled[:, None, :] - train_desc_scaled[None, :, :], axis=2)
    if exclude_self:
        np.fill_diagonal(dists, np.inf)
        k = min(k, train_desc_scaled.shape[0] - 1)
    else:
        k = min(k, train_desc_scaled.shape[0])
    return np.partition(dists, k - 1, axis=1)[:, :k].mean(axis=1)


def _r2_with_size_caveat(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, object]:
    n = len(y_true)
    if n <= 1:
        return {"n": n, "r2": None, "caveat": "too few samples to compute R^2"}
    r2 = round(float(r2_score(y_true, y_pred)), 4)
    if n < MIN_SUBGROUP_N_FOR_STABLE_R2:
        return {"n": n, "r2": r2, "caveat": f"n={n} is below {MIN_SUBGROUP_N_FOR_STABLE_R2} -- treat this R^2 as indicative, not stable"}
    return {"n": n, "r2": r2, "caveat": None}


def main() -> int:
    """Evaluate the champion regressor on the untouched test group, once."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    model = joblib.load(MODEL_PATH)

    x_train, fp_train, y_train = _load_split(data, TRAIN_GROUPS)
    x_cal, fp_cal, y_cal = _load_split(data, [CALIBRATION_GROUP])
    x_test, fp_test, y_test = _load_split(data, [TEST_GROUP])

    desc_train = x_train[:, : x_train.shape[1] - fp_train.shape[1]]
    desc_test = x_test[:, : x_test.shape[1] - fp_test.shape[1]]
    desc_mean = desc_train.mean(axis=0)
    desc_std = desc_train.std(axis=0)
    desc_train_scaled = (desc_train - desc_mean) / np.where(desc_std > 0, desc_std, 1.0)

    y_pred_test = model.predict(x_test)
    global_metrics = {
        "n_test": int(len(y_test)),
        "r2": round(float(r2_score(y_test, y_pred_test)), 4),
        "mae": round(float(mean_absolute_error(y_test, y_pred_test)), 4),
        "rmse": round(float(mean_squared_error(y_test, y_pred_test) ** 0.5), 4),
    }
    print(f"global (scaffold) split test R^2: {global_metrics['r2']:.4f}, MAE: {global_metrics['mae']:.4f} (n={global_metrics['n_test']})", file=sys.stderr)

    y_pred_cal = model.predict(x_cal)
    residuals = np.abs(y_cal - y_pred_cal)
    n_cal = len(residuals)
    q_level = min(1.0, np.ceil((n_cal + 1) * NOMINAL_CONFIDENCE) / n_cal)
    interval_half_width = float(np.quantile(residuals, q_level))

    lower = y_pred_test - interval_half_width
    upper = y_pred_test + interval_half_width
    empirical_coverage = float(np.mean((y_test >= lower) & (y_test <= upper)))

    conformal_result = {
        "method": "split_conformal_prediction_regression",
        "nominal_confidence": NOMINAL_CONFIDENCE,
        "calibration_group": CALIBRATION_GROUP,
        "n_calibration": n_cal,
        "interval_half_width_pki_units": round(interval_half_width, 4),
        "empirical_coverage_on_test": round(empirical_coverage, 4),
        "caveat": f"n_calibration={n_cal} is small -- the calibrated interval width itself carries meaningful sampling noise, on top of what it reports.",
    }
    print(f"conformal: nominal {NOMINAL_CONFIDENCE}, empirical coverage {empirical_coverage:.4f}, half-width {interval_half_width:.4f} pKi units (n_cal={n_cal})", file=sys.stderr)

    max_tanimoto = _tanimoto_max_similarity(fp_test, fp_train)
    knn_dist = _knn_descriptor_distance(desc_test, desc_train_scaled, desc_mean, desc_std, AD_KNN_K)

    tanimoto_threshold = float(np.percentile(_tanimoto_max_similarity(fp_train, fp_train, exclude_self=True), 10))
    knn_threshold = float(np.percentile(_knn_descriptor_distance(desc_train, desc_train_scaled, desc_mean, desc_std, AD_KNN_K, exclude_self=True), 90))

    in_domain = (max_tanimoto >= tanimoto_threshold) & (knn_dist <= knn_threshold)
    ad_result = {
        "method": "tanimoto_max_similarity_and_knn_descriptor_distance",
        "thresholds": {
            "tanimoto_min_for_in_domain": round(tanimoto_threshold, 4),
            "knn_distance_max_for_in_domain": round(knn_threshold, 4),
            "derivation": "10th/90th percentile of the TRAINING population's own self-similarity/self-distance, excluding each compound's guaranteed match to itself.",
        },
        "scaffold_seen_signal": "not available in this pass, same as drd2_activity.",
        "fraction_in_domain": round(float(in_domain.mean()), 4),
        "in_domain": _r2_with_size_caveat(y_test[in_domain], y_pred_test[in_domain]),
        "out_of_domain": _r2_with_size_caveat(y_test[~in_domain], y_pred_test[~in_domain]),
    }
    print(f"applicability domain: {ad_result['fraction_in_domain']:.1%} of test set in-domain (n_test={len(y_test)})", file=sys.stderr)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": train_manifest["algorithm"],
        "label": "pki (continuous, higher = stronger predicted HRH1 binding)",
        "global_split": {
            **global_metrics,
            "description": "Scaffold-level split_group 9, per ADR-009. Touched once, here.",
        },
        "conformal": conformal_result,
        "applicability_domain": ad_result,
        "external_validation": {
            "performed": False,
            "reason": "No independent second-source HRH1 dataset identified in this pass -- same situation as DRD2.",
        },
        "limitations": [
            "Dataset is small (1,395 compounds total, 916 for training) -- comparable in size to CYP2D6's "
            "1,394 records, which Phase 9 already rejected as too small for a robust scaffold-split "
            "protocol in that context. HRH1 proceeds here anyway because, unlike CYP2D6 (which was "
            "competing against a larger alternative, CYP3A4, for one endpoint slot), HRH1 has no "
            "substitute for this feature's own selectivity requirement -- but every metric below should "
            "be read with that size firmly in mind, not treated as equivalent in reliability to DRD2's.",
            "Classical models only in this pass; no GNN benchmark (dataset is far too small for one).",
            "Applicability domain's scaffold-seen signal is not available in this pass.",
            "No external validation performed in this pass.",
            "This model is not integrated into the live /predict API -- offline evaluation only.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
