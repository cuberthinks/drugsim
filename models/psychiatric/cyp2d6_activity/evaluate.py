#!/usr/bin/env python3
"""Evaluate the CYP2D6 classifier on the held-out test group -- touched once, here.

Combines two already-established patterns in this repository rather than
inventing a third: `models/admet/cyp3a4_inhibition/evaluate.py` +
`reliability.py`'s binary classification metrics and split-conformal
prediction-set methodology, and `models/psychiatric/drd2_activity/
evaluate.py`'s Tanimoto-max-similarity + k-NN descriptor-distance
applicability domain (WITH the exclude-self correction applied from the
start -- see that file's docstring for the bug this guards against).

Usage:
    python models/psychiatric/cyp2d6_activity/evaluate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp2d6_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "evaluation_report.json"

TRAIN_GROUPS = list(range(7))
CALIBRATION_GROUP = 7
TEST_GROUP = 9
NOMINAL_CONFIDENCE = 0.90
AD_KNN_K = 5


def _load_split(data: dict, groups: list[int]) -> dict[str, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    return {
        "x": np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1),
        "descriptors": data["descriptors"][mask],
        "fingerprints": data["fingerprints"][mask],
        "y": data["labels"][mask],
    }


def _binary_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, object]:
    y_pred = (y_prob >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    sensitivity = tp / (tp + fn) if (tp + fn) > 0 else None
    specificity = tn / (tn + fp) if (tn + fp) > 0 else None
    return {
        "n_test": int(len(y_true)),
        "positive_fraction": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "average_precision_pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "matthews_corrcoef": round(float(matthews_corrcoef(y_true, y_pred)), 4),
        "sensitivity_recall_positive": round(float(sensitivity), 4) if sensitivity is not None else None,
        "specificity_recall_negative": round(float(specificity), 4) if specificity is not None else None,
        "f1": round(float(f1_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred)), 4),
        "recall": round(float(recall_score(y_true, y_pred)), 4),
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def _tanimoto_max_similarity(query_fps: np.ndarray, train_fps: np.ndarray, exclude_self: bool = False) -> np.ndarray:
    """Max Tanimoto similarity of each query fingerprint to any training fingerprint.

    `exclude_self` must be True when query_fps IS train_fps -- otherwise
    every compound's guaranteed match to itself (similarity 1.0) collapses
    any percentile-based threshold derived from this population. See
    drd2_activity/evaluate.py's identical function docstring for the bug
    this guards against (first caught and fixed there).
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


def main() -> int:
    """Evaluate the champion classifier on the untouched test group, once."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    model = joblib.load(MODEL_PATH)

    train = _load_split(data, TRAIN_GROUPS)
    cal = _load_split(data, [CALIBRATION_GROUP])
    test = _load_split(data, [TEST_GROUP])

    desc_mean = train["descriptors"].mean(axis=0)
    desc_std = train["descriptors"].std(axis=0)
    desc_train_scaled = (train["descriptors"] - desc_mean) / np.where(desc_std > 0, desc_std, 1.0)

    # --- 1. Global classification metrics on the untouched test group ---
    y_prob_test = model.predict_proba(test["x"])[:, 1]
    global_metrics = _binary_metrics(test["y"], y_prob_test)
    print(f"global (scaffold) split test ROC-AUC: {global_metrics['roc_auc']:.4f} (n={global_metrics['n_test']})", file=sys.stderr)

    # --- 2. Split conformal prediction (classification), mirroring
    # cyp3a4_inhibition/reliability.py's methodology exactly ---
    cal_probs = model.predict_proba(cal["x"])
    cal_true_class_prob = np.where(cal["y"] == 1, cal_probs[:, 1], cal_probs[:, 0])
    cal_nonconformity = 1.0 - cal_true_class_prob
    n_cal = len(cal_nonconformity)
    epsilon = 1.0 - NOMINAL_CONFIDENCE

    test_probs = model.predict_proba(test["x"])

    def _p_value(candidate_prob_col: np.ndarray) -> np.ndarray:
        alpha_candidate = 1.0 - candidate_prob_col
        counts = (cal_nonconformity[None, :] >= alpha_candidate[:, None]).sum(axis=1)
        return (counts + 1) / (n_cal + 1)

    p0 = _p_value(test_probs[:, 0])
    p1 = _p_value(test_probs[:, 1])
    include_0 = p0 > epsilon
    include_1 = p1 > epsilon
    prediction_sets = [
        ({0, 1} if (i0 and i1) else ({0} if i0 else ({1} if i1 else set())))
        for i0, i1 in zip(include_0, include_1)
    ]
    covered = [int(test["y"][i]) in prediction_sets[i] for i in range(len(test["y"]))]
    empirical_coverage = float(np.mean(covered))
    set_sizes = [len(s) for s in prediction_sets]
    n_singleton = sum(1 for s in set_sizes if s == 1)
    n_uncertain = sum(1 for s in set_sizes if s == 2)
    n_empty = sum(1 for s in set_sizes if s == 0)

    singleton_mask = np.array(set_sizes) == 1
    singleton_correct = [
        (list(prediction_sets[i])[0] == int(test["y"][i])) for i in range(len(test["y"])) if singleton_mask[i]
    ]
    uncertain_mask = np.array(set_sizes) == 2
    y_pred_raw = (y_prob_test >= 0.5).astype(int)
    uncertain_correct = [
        (y_pred_raw[i] == int(test["y"][i])) for i in range(len(test["y"])) if uncertain_mask[i]
    ]

    conformal_result = {
        "method": "split_conformal_prediction_classification",
        "nominal_confidence": NOMINAL_CONFIDENCE,
        "n_calibration": n_cal,
        "n_test": len(test["y"]),
        "empirical_coverage": round(empirical_coverage, 4),
        "coverage_within_tolerance": bool(empirical_coverage >= NOMINAL_CONFIDENCE - 0.05),
        "prediction_set_sizes": {
            "singleton_confident": n_singleton,
            "both_classes_uncertain": n_uncertain,
            "empty_anomalous": n_empty,
        },
        "singleton_fraction": round(n_singleton / len(test["y"]), 4),
        "accuracy_when_singleton": round(float(np.mean(singleton_correct)), 4) if singleton_correct else None,
        "accuracy_when_uncertain_both_classes": round(float(np.mean(uncertain_correct)), 4) if uncertain_correct else None,
    }
    print(f"conformal: nominal {NOMINAL_CONFIDENCE}, empirical coverage {empirical_coverage:.4f} (n_cal={n_cal})", file=sys.stderr)

    # --- 3. Applicability domain, exclude-self-fixed thresholds ---
    max_tanimoto = _tanimoto_max_similarity(test["fingerprints"], train["fingerprints"])
    knn_dist = _knn_descriptor_distance(test["descriptors"], desc_train_scaled, desc_mean, desc_std, AD_KNN_K)

    tanimoto_threshold = float(np.percentile(_tanimoto_max_similarity(train["fingerprints"], train["fingerprints"], exclude_self=True), 10))
    knn_threshold = float(np.percentile(_knn_descriptor_distance(train["descriptors"], desc_train_scaled, desc_mean, desc_std, AD_KNN_K, exclude_self=True), 90))

    in_domain = (max_tanimoto >= tanimoto_threshold) & (knn_dist <= knn_threshold)
    y_pred_test = (y_prob_test >= 0.5).astype(int)

    def _acc_with_size_caveat(mask: np.ndarray) -> dict[str, object]:
        n = int(mask.sum())
        if n == 0:
            return {"n": 0, "accuracy": None, "roc_auc": None}
        acc = round(float((y_pred_test[mask] == test["y"][mask]).mean()), 4)
        roc = round(float(roc_auc_score(test["y"][mask], y_prob_test[mask])), 4) if len(set(test["y"][mask])) > 1 else None
        return {"n": n, "accuracy": acc, "roc_auc": roc}

    ad_result = {
        "method": "tanimoto_max_similarity_and_knn_descriptor_distance",
        "thresholds": {
            "tanimoto_min_for_in_domain": round(tanimoto_threshold, 4),
            "knn_distance_max_for_in_domain": round(knn_threshold, 4),
            "derivation": "10th/90th percentile of the TRAINING population's own self-similarity/self-distance, excluding each compound's guaranteed match to itself.",
        },
        "fraction_in_domain": round(float(in_domain.mean()), 4),
        "in_domain": _acc_with_size_caveat(in_domain),
        "out_of_domain": _acc_with_size_caveat(~in_domain),
    }
    print(f"applicability domain: {ad_result['fraction_in_domain']:.1%} of test set in-domain (n_test={len(test['y'])})", file=sys.stderr)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": train_manifest["algorithm"],
        "label": "binary CYP2D6-inhibitor liability (1=inhibitor, aggregated IC50 <= 10 uM)",
        "global_split": {
            **global_metrics,
            "description": "Scaffold-level split_group 9, per ADR-009. Touched once, here.",
        },
        "conformal": conformal_result,
        "applicability_domain": ad_result,
        "external_validation": {
            "performed": False,
            "reason": "No independent second-source CYP2D6 dataset identified in this pass, same situation as DRD2/HRH1.",
        },
        "limitations": [
            "This is a CYP2D6-inhibition-liability flag only -- it cannot infer a patient's own "
            "CYP2D6 genotype/phenotype (poor/intermediate/extensive/ultrarapid metabolizer status). "
            "'Not a CYP2D6 inhibitor' does not mean 'safe for poor metabolizers' -- those are "
            "distinct concepts, per scientific-foundation.md.",
            "10 uM inhibitor threshold is a literature screening convention, not a universal "
            "biological constant -- same convention class already used for hERG and CYP3A4.",
            "Classical models only in this pass; no GNN benchmark (small-data regime, no existing "
            "GNN infrastructure in this repository).",
            "No external validation performed in this pass.",
            "This model is not integrated into the live /predict API -- offline evaluation only.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
