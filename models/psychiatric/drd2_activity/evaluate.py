#!/usr/bin/env python3
"""Evaluate the DRD2 regressor on the held-out test group -- touched once, here.

Mirrors the spirit of `models/admet/herg_inhibition/evaluate.py` and
`reliability.py` combined into one script, adapted for a regression
target:

1. Global (scaffold) split test metrics: R^2, MAE, RMSE on split_group 9,
   touched here for the first and only time.
2. Split conformal PREDICTION INTERVALS (the regression analogue of
   classification conformal p-values): calibrated on split_group 7,
   producing a nominal-90%-coverage interval width, then checked for
   real empirical coverage on the test set.
3. Applicability domain: same conceptual method already used for hERG/
   CYP3A4 (max Tanimoto similarity to training fingerprints, kNN
   descriptor distance, scaffold-seen-in-training) -- implemented
   standalone here for this offline evaluation, since wiring it into
   the live `drugsim_predict` applicability-domain module is a
   separately-scoped step (this pipeline's own step 11, "API
   integration" -- see docs/psychiatric-pipeline/data-sources.md).

**External validation**: not performed in this pass. This endpoint has
no independent second-source dataset identified yet (unlike hERG's
PubChem external set or CYP3A4's TDC external set) -- stated here
plainly as a real, disclosed limitation rather than skipped silently.

Usage:
    python models/psychiatric/drd2_activity/evaluate.py
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
FEATURES_NPZ = ROOT / "datasets" / "processed" / "drd2_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "evaluation_report.json"

TRAIN_GROUPS = list(range(7))
CALIBRATION_GROUP = 7
TEST_GROUP = 9
NOMINAL_CONFIDENCE = 0.90

# Applicability-domain thresholds: the training-population 10th/90th
# percentile of each signal, computed below rather than hardcoded --
# same principle as hERG/CYP3A4's own AD thresholds being derived from
# the training distribution, not an arbitrary constant.
AD_KNN_K = 5


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    descriptors = data["descriptors"][mask]
    fingerprints = data["fingerprints"][mask]
    x = np.concatenate([descriptors, fingerprints], axis=1)
    y = data["labels"][mask]
    return x, fingerprints, y


def _tanimoto_max_similarity(query_fps: np.ndarray, train_fps: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    """Max Tanimoto similarity of each query fingerprint to any training fingerprint.

    Vectorised over bit-packed 0/1 fingerprints: Tanimoto(a,b) = |a&b| / |a|+|b|-|a&b|.

    `exclude_self` must be True when query_fps IS train_fps (deriving a
    threshold FROM the training population's own self-similarity) --
    otherwise every compound's guaranteed identical match to itself
    (similarity 1.0) dominates the distribution and any percentile below
    the 100th collapses to 1.0, an impossible-to-pass threshold. Caught
    by inspection during this evaluation: an early version of this
    threshold, computed without this exclusion, put 99.4% of the real
    test set "out of domain" -- a bug in the threshold, not a real
    finding about the model.
    """
    train_fps = train_fps.astype(np.float32)
    query_fps = query_fps.astype(np.float32)
    intersection = query_fps @ train_fps.T  # (n_query, n_train)
    query_popcount = query_fps.sum(axis=1, keepdims=True)
    train_popcount = train_fps.sum(axis=1, keepdims=True).T
    union = query_popcount + train_popcount - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        tanimoto = np.where(union > 0, intersection / union, 0.0)
    if exclude_self:
        np.fill_diagonal(tanimoto, -1.0)
    return tanimoto.max(axis=1)


def _knn_descriptor_distance(query_desc: np.ndarray, train_desc_scaled: np.ndarray, mean: np.ndarray, std: np.ndarray, k: int, exclude_self: bool = False) -> np.ndarray:
    """Mean distance to the k nearest training compounds in scaled descriptor space.

    `exclude_self` (see `_tanimoto_max_similarity`'s docstring for the
    same issue) must be True when deriving a threshold from the training
    population against itself -- otherwise every compound's guaranteed
    zero-distance match to itself is included among its "k nearest
    neighbours," biasing the derived threshold toward zero.
    """
    scaled = (query_desc - mean) / np.where(std > 0, std, 1.0)
    dists = np.linalg.norm(scaled[:, None, :] - train_desc_scaled[None, :, :], axis=2)
    if exclude_self:
        np.fill_diagonal(dists, np.inf)
        k = min(k, train_desc_scaled.shape[0] - 1)
    else:
        k = min(k, train_desc_scaled.shape[0])
    return np.partition(dists, k - 1, axis=1)[:, :k].mean(axis=1)


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

    # -- 1. Global (scaffold) split: the honest number. Group 9, touched
    # here for the first and only time in this pipeline. --
    y_pred_test = model.predict(x_test)
    global_metrics = {
        "n_test": int(len(y_test)),
        "r2": round(float(r2_score(y_test, y_pred_test)), 4),
        "mae": round(float(mean_absolute_error(y_test, y_pred_test)), 4),
        "rmse": round(float(mean_squared_error(y_test, y_pred_test) ** 0.5), 4),
    }
    print(f"global (scaffold) split test R^2: {global_metrics['r2']:.4f}, MAE: {global_metrics['mae']:.4f}", file=sys.stderr)

    # -- 2. Split conformal prediction intervals. Calibrate the interval
    # half-width on group 7 (never touched in training or here for
    # anything else), then check its REAL coverage on group 9. --
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
        "note": (
            "interval_half_width is in pKi units (log-scale) -- e.g. a half-width of 1.0 means the "
            "90% interval spans two orders of magnitude in Ki. A wide interval is an honest signal "
            "of low confidence, not a defect to hide."
        ),
    }
    print(f"conformal: nominal {NOMINAL_CONFIDENCE}, empirical coverage {empirical_coverage:.4f}, half-width {interval_half_width:.4f} pKi units", file=sys.stderr)

    # -- 3. Applicability domain: max Tanimoto similarity + kNN descriptor
    # distance + scaffold-seen, same conceptual method as hERG/CYP3A4,
    # implemented standalone for this offline evaluation. --
    max_tanimoto = _tanimoto_max_similarity(fp_test, fp_train)
    knn_dist = _knn_descriptor_distance(desc_test, desc_train_scaled, desc_mean, desc_std, AD_KNN_K)
    # A scaffold-seen signal (as hERG/CYP3A4's AD reports) would require the
    # bemis_murcko_scaffold column, which prepare_features.py does not persist
    # in the .npz archive -- reported as unavailable below rather than faked.

    tanimoto_threshold = float(np.percentile(_tanimoto_max_similarity(fp_train, fp_train, exclude_self=True), 10))
    knn_threshold = float(np.percentile(_knn_descriptor_distance(desc_train, desc_train_scaled, desc_mean, desc_std, AD_KNN_K, exclude_self=True), 90))

    in_domain = (max_tanimoto >= tanimoto_threshold) & (knn_dist <= knn_threshold)
    ad_result = {
        "method": "tanimoto_max_similarity_and_knn_descriptor_distance",
        "thresholds": {
            "tanimoto_min_for_in_domain": round(tanimoto_threshold, 4),
            "knn_distance_max_for_in_domain": round(knn_threshold, 4),
            "derivation": "10th/90th percentile of the TRAINING population's own self-similarity/self-distance -- not an arbitrary constant.",
        },
        "scaffold_seen_signal": "not available in this pass -- bemis_murcko_scaffold is not persisted in the .npz feature archive; would need prepare_features.py extended to carry it through, a small follow-up not done here.",
        "fraction_in_domain": round(float(in_domain.mean()), 4),
        "mean_r2_in_domain": round(float(r2_score(y_test[in_domain], y_pred_test[in_domain])), 4) if in_domain.sum() > 1 else None,
        "mean_r2_out_of_domain": round(float(r2_score(y_test[~in_domain], y_pred_test[~in_domain])), 4) if (~in_domain).sum() > 1 else None,
    }
    print(f"applicability domain: {ad_result['fraction_in_domain']:.1%} of test set in-domain", file=sys.stderr)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": train_manifest["algorithm"],
        "label": "pki (continuous, higher = stronger predicted DRD2 binding)",
        "global_split": {
            **global_metrics,
            "description": "Scaffold-level split_group 9, per ADR-009. Touched once, here.",
        },
        "conformal": conformal_result,
        "applicability_domain": ad_result,
        "external_validation": {
            "performed": False,
            "reason": (
                "No independent second-source DRD2 dataset has been identified/downloaded in this "
                "pass (unlike hERG's PubChem external set or CYP3A4's TDC external set). Stated "
                "plainly as a real limitation, not silently skipped. BindingDB (already registered in "
                "datasets/registry.yaml with role: binding_affinity) is the most plausible candidate "
                "for a future external check, given heavy documented overlap with ChEMBL that would "
                "need deduplication first."
            ),
        },
        "limitations": [
            "Classical models only in this pass (Random Forest selected); no GNN benchmark run -- see train_manifest.json's gnn_benchmark note.",
            "Applicability domain's scaffold-seen signal is not available in this pass (not persisted in the feature archive).",
            "No external validation performed in this pass.",
            "This model is not integrated into the live /predict API -- offline evaluation only, per this feature's phased build order.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
