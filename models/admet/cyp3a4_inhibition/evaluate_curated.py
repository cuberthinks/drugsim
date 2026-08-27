#!/usr/bin/env python3
"""Evaluate the curated-data CYP3A4 model, and cross-check it against production.

Phase 12 companion to `evaluate.py`, mirroring
`models/admet/herg_inhibition/evaluate_curated.py` -- see that file for the
full rationale of the two-report design and the cross-evaluation grid.

Unlike hERG, CYP3A4's deployed `artifact/model.joblib` has no tree-count
truncation (`models/registry/cyp3a4_inhibition_v1.json` records
`n_estimators: 500` with no `deployment_variant` block), and
`train_curated.py` independently selected 500 trees too -- so there is no
tree-count confound here, and the cross-evaluation grid is a single,
direct comparison.

`_binary_metrics` includes MCC and explicit sensitivity/specificity,
matching CYP3A4's own `evaluate.py` convention (kept off hERG's per the
do-not-modify-hERG rule already documented there).

Usage:
    python models/admet/cyp3a4_inhibition/evaluate_curated.py
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
PRODUCTION_FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
CURATED_FEATURES_NPZ = ROOT / "datasets" / "curated" / "cyp3a4_inhibition_features_curated.npz"
PRODUCTION_MODEL_PATH = Path(__file__).resolve().parent / "artifact" / "model.joblib"
EXPERIMENT_DIR = Path(__file__).resolve().parent / "experiments" / "curated_v1"
CURATED_MODEL_PATH = EXPERIMENT_DIR / "artifact" / "model.joblib"
OWN_EVAL_JSON = EXPERIMENT_DIR / "evaluation_report.json"
CROSS_EVAL_JSON = EXPERIMENT_DIR / "cross_evaluation_report.json"

TEST_GROUP = 9


def _load_test(npz_path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = np.load(npz_path, allow_pickle=True)
    mask = data["split_groups"] == TEST_GROUP
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


def _bootstrap_ci(y_true: np.ndarray, y_prob: np.ndarray, n_boot: int = 1000, seed: int = 42) -> dict[str, float]:
    """95% bootstrap confidence interval for ROC-AUC, matching evaluate.py."""
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
        "f1": round(float(f1_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred)), 4),
        "recall": round(float(recall_score(y_true, y_pred)), 4),
        "matthews_corrcoef": round(float(matthews_corrcoef(y_true, y_pred)), 4),
        "sensitivity_recall_positive": round(float(sensitivity), 4) if sensitivity is not None else None,
        "specificity_recall_negative": round(float(specificity), 4) if specificity is not None else None,
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def main() -> int:
    """Evaluate the curated model on its own holdout, then cross-evaluate against production."""
    x_test_curated, y_test_curated = _load_test(CURATED_FEATURES_NPZ)
    x_test_production, y_test_production = _load_test(PRODUCTION_FEATURES_NPZ)

    curated_model = joblib.load(CURATED_MODEL_PATH)
    production_model = joblib.load(PRODUCTION_MODEL_PATH)

    # -- 1. Own-population evaluation. --
    own_probs = curated_model.predict_proba(x_test_curated)[:, 1]
    own_metrics = _binary_metrics(y_test_curated, own_probs)
    own_ci = _bootstrap_ci(y_test_curated, own_probs)
    print(f"curated model, curated test set, ROC-AUC: {own_metrics['roc_auc']:.4f}", file=sys.stderr)

    own_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "random_forest",
        "global_split": {
            **own_metrics,
            "confidence_interval_95pct": own_ci,
            "description": "Scaffold-level split_group 9 of the curated, training_eligible=True population.",
        },
        "note": (
            "No random-split benchmark-proxy retrain here -- that ablation is already reported once "
            "against production data in evaluate.py's own evaluation_report.json and answers a "
            "different question (the cost of scaffold splitting itself, not the effect of curation)."
        ),
    }
    OWN_EVAL_JSON.write_text(json.dumps(own_report, indent=2) + "\n", encoding="utf-8")

    # -- 2. Cross-evaluation grid. CYP3A4 has no tree-count truncation
    # (unlike hERG), so this is a single, direct 2x2 grid. --
    cells = {
        "production_model_x_production_test": _binary_metrics(
            y_test_production, production_model.predict_proba(x_test_production)[:, 1]
        ),
        "production_model_x_curated_test": _binary_metrics(
            y_test_curated, production_model.predict_proba(x_test_curated)[:, 1]
        ),
        "curated_model_x_production_test": _binary_metrics(
            y_test_production, curated_model.predict_proba(x_test_production)[:, 1]
        ),
        "curated_model_x_curated_test": _binary_metrics(
            y_test_curated, curated_model.predict_proba(x_test_curated)[:, 1]
        ),
    }

    headline_delta = round(
        cells["curated_model_x_curated_test"]["roc_auc"] - cells["production_model_x_production_test"]["roc_auc"], 4
    )

    same_population = (
        x_test_curated.shape[0] == x_test_production.shape[0]
        and np.array_equal(y_test_curated, y_test_production)
        and np.array_equal(x_test_curated, x_test_production)
    )

    cross_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_populations": {
            "production_test_n": int(x_test_production.shape[0]),
            "curated_test_n": int(x_test_curated.shape[0]),
            "identical_test_populations": same_population,
        },
        "cells": {
            name: {**metrics, "description": desc}
            for (name, metrics), desc in zip(
                cells.items(),
                [
                    "Production model, scored on production's own held-out test group 9 (the number in evaluate.py's evaluation_report.json).",
                    "Production model, scored on the curated pipeline's held-out test group 9 -- does the production model generalise to the (possibly different) curated-eligible population?",
                    "Curated-data-trained model, scored on production's held-out test group 9 -- does training on curated data hurt or help generalisation back onto the full original population, including compounds curation would exclude from training?",
                    "Curated-data-trained model, scored on the curated pipeline's own held-out test group 9 -- this model's native holdout, directly comparable to the first cell.",
                ],
            )
        },
        "headline_roc_auc_delta": headline_delta,
        "headline_delta_explanation": (
            f"curated_model_x_curated_test ROC-AUC minus production_model_x_production_test ROC-AUC = "
            f"{headline_delta:+.4f} -- each model evaluated on its own native holdout. Both models use "
            f"500 trees (CYP3A4 has no memory-driven truncation, unlike hERG), so no tree-count confound. "
            + (
                "The two test populations are identical (same compounds, same labels, same split "
                "assignment) for CYP3A4, so this delta isolates pure training/evaluation noise (e.g. "
                "RandomForestClassifier's parallel-fit nondeterminism), not a real difference in what "
                "data the models saw."
                if same_population
                else "The two test populations differ, so this delta reflects both any modelling "
                "difference and any difference in which compounds ended up in each test set."
            )
        ),
    }
    CROSS_EVAL_JSON.write_text(json.dumps(cross_report, indent=2) + "\n", encoding="utf-8")

    print(f"\nheadline ROC-AUC delta (curated - production): {headline_delta:+.4f}")
    print(f"own-population report: {OWN_EVAL_JSON}")
    print(f"cross-evaluation report: {CROSS_EVAL_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
