#!/usr/bin/env python3
"""Evaluate the CYP3A4 model on the held-out test group -- touched once, here.

Mirrors ``models/admet/herg_inhibition/evaluate.py``: dual-split reporting
(global scaffold split + a random-split benchmark proxy), same limitation
noted (no true TDC-canonical split exists for this exact ChEMBL-sourced
compound set). Adds MCC and specificity/sensitivity explicitly, since
Phase 9 Sec 8 names them for classification endpoints (the hERG script
predates that explicit ask; not retrofitted onto hERG per the
do-not-modify-hERG rule, but included here from the start).

Usage:
    python models/admet/cyp3a4_inhibition/evaluate.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
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
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "evaluation_report.json"

TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9
RANDOM_SPLIT_SEED = 42


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


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


def _bootstrap_ci(y_true: np.ndarray, y_prob: np.ndarray, n_boot: int = 1000, seed: int = 42) -> dict[str, float]:
    """95% bootstrap confidence interval for ROC-AUC (Phase 9 Sec 8: "report
    confidence intervals where practical")."""
    rng = np.random.default_rng(seed)
    n = len(y_true)
    aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        y_b, p_b = y_true[idx], y_prob[idx]
        if len(np.unique(y_b)) < 2:
            continue
        aucs.append(roc_auc_score(y_b, p_b))
    aucs = np.array(aucs)
    return {
        "roc_auc_ci_lower_2.5pct": round(float(np.percentile(aucs, 2.5)), 4),
        "roc_auc_ci_upper_97.5pct": round(float(np.percentile(aucs, 97.5)), 4),
        "n_bootstrap_replicates": int(len(aucs)),
    }


def main() -> int:
    """Evaluate the champion model on the untouched test group, once."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    model = joblib.load(MODEL_PATH)

    x_test, y_test = _load_split(data, [TEST_GROUP])
    y_prob_global = model.predict_proba(x_test)[:, 1]
    global_metrics = _binary_metrics(y_test, y_prob_global)
    ci = _bootstrap_ci(y_test, y_prob_global)
    print(f"global (scaffold) split test ROC-AUC: {global_metrics['roc_auc']:.4f} (95% CI [{ci['roc_auc_ci_lower_2.5pct']}, {ci['roc_auc_ci_upper_97.5pct']}])", file=sys.stderr)

    x_all = np.concatenate([data["descriptors"], data["fingerprints"]], axis=1)
    y_all = data["labels"]
    random_split_test_fraction = len(y_test) / len(y_all)
    x_tr, x_te, y_tr, y_te = train_test_split(
        x_all, y_all, test_size=random_split_test_fraction, random_state=RANDOM_SPLIT_SEED, stratify=y_all
    )
    params = train_manifest["hyperparameters"]
    random_split_model = RandomForestClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        class_weight="balanced",
        random_state=train_manifest["random_seed"],
        n_jobs=-1,
    )
    random_split_model.fit(x_tr, y_tr)
    y_prob_benchmark = random_split_model.predict_proba(x_te)[:, 1]
    benchmark_metrics = _binary_metrics(y_te, y_prob_benchmark)
    print(f"benchmark (random split) proxy test ROC-AUC: {benchmark_metrics['roc_auc']:.4f}", file=sys.stderr)

    gap = round(benchmark_metrics["roc_auc"] - global_metrics["roc_auc"], 4)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": train_manifest["algorithm"],
        "global_split": {
            **global_metrics,
            "confidence_interval_95pct": ci,
            "description": "Scaffold-level split_group 9, per ADR-009. Touched once, here.",
        },
        "benchmark_split": {
            **benchmark_metrics,
            "description": (
                "Random-split PROXY, not a true TDC canonical benchmark split -- no TDC split exists "
                "for this exact ChEMBL-sourced compound set. Same model config, same data pool, same "
                "test fraction, stratified random assignment instead of scaffold."
            ),
        },
        "roc_auc_gap": gap,
        "gap_explanation": (
            "Global scaffold splitting prevents cross-dataset/near-neighbour leakage; the random-split "
            "proxy is optimistic because structurally near-identical compounds (same scaffold, minor "
            f"substituent changes) can appear in both its train and test sets. The {gap:+.4f} ROC-AUC "
            "gap is the leakage the scaffold split is removing, not a property of the model changing "
            "between the two runs."
        ),
        "limitation": (
            "Not a TDC-comparable leaderboard number -- a within-dataset random-vs-scaffold ablation on "
            "the same ChEMBL-sourced compounds, included because a true external benchmark split does "
            "not exist for this dataset."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nROC-AUC gap (benchmark-proxy minus global): {gap:+.4f}")
    print(f"report: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
