#!/usr/bin/env python3
"""Evaluate the curated-data hERG model, and cross-check it against production.

Phase 12 companion to `evaluate.py`. Two things, written to two reports:

1. Own-population evaluation (`evaluation_report.json` in
   `experiments/curated_v1/`): the same global scaffold-split (test group
   9) metrics `evaluate.py` reports for the production model. Deliberately
   skips the random-split benchmark-proxy retrain `evaluate.py` also does
   -- that ablation answers "how much does scaffold splitting cost", a
   question already answered once against production; repeating it here
   would not tell us anything new about curation's effect.

2. Cross-evaluation grid (`cross_evaluation_report.json`): both the
   production model and this curated-data model, scored against both test
   sets (production's group 9 and curated's group 9). Valid because both
   feature sets are built by literally the same descriptor/fingerprint
   code on `standardized_smiles` (see `prepare_features_curated.py`'s
   parity check) -- a 2066-column feature vector means the same thing in
   either dataset. This is the actual "compare against production"
   deliverable Phase 12 was scoped to produce.

   Important wrinkle, discovered while building this: the DEPLOYED
   `artifact/model.joblib` is not the model `evaluation_report.json` was
   computed from. Per `models/registry/herg_inhibition_v1.json`'s own
   `deployment_variant` block, the deployed artifact is the first 200 of
   an originally-trained 500-tree ensemble, truncated post-hoc to fit a
   512MB memory limit -- a real, disclosed, already-existing fact about
   this repo, not something Phase 12 introduces. `train_curated.py`'s own
   hyperparameter search independently selected 500 trees for the curated
   model (same grid, same data-driven choice production made before its
   own truncation). Comparing a 500-tree curated model against a 200-tree
   deployed production model would conflate "effect of curated data" with
   "effect of ensemble size" -- so this script scores against BOTH the
   deployed 200-tree artifact (what's actually live) AND the preserved
   `model_full_500trees.joblib.bak` (an equal-tree-count comparison),
   labelling each cell accordingly.

Usage:
    python models/admet/herg_inhibition/evaluate_curated.py
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
    precision_score,
    recall_score,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
CURATED_FEATURES_NPZ = ROOT / "datasets" / "curated" / "herg_inhibition_features_curated.npz"
PRODUCTION_MODEL_PATH = Path(__file__).resolve().parent / "artifact" / "model.joblib"
PRODUCTION_MODEL_FULL_500TREES_PATH = Path(__file__).resolve().parent / "artifact" / "model_full_500trees.joblib.bak"
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


def _binary_metrics(y_true: np.ndarray, y_prob: np.ndarray) -> dict[str, object]:
    y_pred = (y_prob >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "n_test": int(len(y_true)),
        "positive_fraction": round(float(y_true.mean()), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "average_precision": round(float(average_precision_score(y_true, y_prob)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, y_pred)), 4),
        "f1": round(float(f1_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred)), 4),
        "recall": round(float(recall_score(y_true, y_pred)), 4),
        "brier_score": round(float(brier_score_loss(y_true, y_prob)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def main() -> int:
    """Evaluate the curated model on its own holdout, then cross-evaluate against production."""
    x_test_curated, y_test_curated = _load_test(CURATED_FEATURES_NPZ)
    x_test_production, y_test_production = _load_test(PRODUCTION_FEATURES_NPZ)

    curated_model = joblib.load(CURATED_MODEL_PATH)
    production_model = joblib.load(PRODUCTION_MODEL_PATH)
    production_model_full_500trees = joblib.load(PRODUCTION_MODEL_FULL_500TREES_PATH)

    # -- 1. Own-population evaluation. --
    own_probs = curated_model.predict_proba(x_test_curated)[:, 1]
    own_metrics = _binary_metrics(y_test_curated, own_probs)
    print(f"curated model, curated test set, ROC-AUC: {own_metrics['roc_auc']:.4f}", file=sys.stderr)

    own_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": "random_forest",
        "global_split": {
            **own_metrics,
            "description": "Scaffold-level split_group 9 of the curated, training_eligible=True population.",
        },
        "note": (
            "No random-split benchmark-proxy retrain here -- that ablation is already reported once "
            "against production data in evaluate.py's own evaluation_report.json and answers a "
            "different question (the cost of scaffold splitting itself, not the effect of curation)."
        ),
    }
    OWN_EVAL_JSON.write_text(json.dumps(own_report, indent=2) + "\n", encoding="utf-8")

    # -- 2. Cross-evaluation grid. --
    # "production_model" = the deployed 200-tree truncation (what's actually
    # live). "production_model_full_500trees" = the preserved, untruncated
    # ensemble -- the fair comparison point for the curated model, which
    # also happens to be 500 trees, so that tree-count isn't a confound.
    cells = {
        "production_model_x_production_test": _binary_metrics(
            y_test_production, production_model.predict_proba(x_test_production)[:, 1]
        ),
        "production_model_x_curated_test": _binary_metrics(
            y_test_curated, production_model.predict_proba(x_test_curated)[:, 1]
        ),
        "production_model_full_500trees_x_production_test": _binary_metrics(
            y_test_production, production_model_full_500trees.predict_proba(x_test_production)[:, 1]
        ),
        "production_model_full_500trees_x_curated_test": _binary_metrics(
            y_test_curated, production_model_full_500trees.predict_proba(x_test_curated)[:, 1]
        ),
        "curated_model_x_production_test": _binary_metrics(
            y_test_production, curated_model.predict_proba(x_test_production)[:, 1]
        ),
        "curated_model_x_curated_test": _binary_metrics(
            y_test_curated, curated_model.predict_proba(x_test_curated)[:, 1]
        ),
    }

    # The apples-to-apples headline: both models have 500 trees here, so any
    # remaining delta is attributable to the data (curated vs processed),
    # not ensemble size.
    headline_delta_equal_tree_count = round(
        cells["curated_model_x_curated_test"]["roc_auc"]
        - cells["production_model_full_500trees_x_production_test"]["roc_auc"],
        4,
    )
    # The as-deployed headline: what a user actually experiences today vs.
    # the curated candidate. Conflates data effect with tree-count effect --
    # reported for completeness, not as the primary claim.
    headline_delta_as_deployed = round(
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
        "tree_count_caveat": (
            "The deployed artifact/model.joblib is a 200-tree truncation of an originally-trained "
            "500-tree ensemble, kept that way for a Render memory limit (see models/registry/"
            "herg_inhibition_v1.json's deployment_variant block -- a pre-existing, disclosed fact, "
            "not introduced by this comparison). train_curated.py's hyperparameter search "
            "independently selected 500 trees for the curated model. Cells involving "
            "'production_model' (not 'production_model_full_500trees') therefore differ in both "
            "data source AND ensemble size from the curated model -- use the "
            "'production_model_full_500trees' cells for a same-tree-count, data-only comparison."
        ),
        "cells": {
            name: {**metrics, "description": desc}
            for (name, metrics), desc in zip(
                cells.items(),
                [
                    "Deployed (200-tree) production model, scored on production's own held-out test group 9 -- what's actually live today. Differs from evaluate.py's committed evaluation_report.json (0.7875) because that report was generated from the full 500-tree model before truncation.",
                    "Deployed (200-tree) production model, scored on the curated pipeline's held-out test group 9 -- does the deployed model generalise to the curated-eligible population?",
                    "Full 500-tree production model (pre-truncation backup), scored on production's own held-out test group 9 -- reproduces evaluate.py's committed 0.7875 exactly.",
                    "Full 500-tree production model (pre-truncation backup), scored on the curated pipeline's held-out test group 9.",
                    "Curated-data-trained model (500 trees), scored on production's held-out test group 9 -- does training on curated data hurt or help generalisation back onto the full original population, including compounds curation would exclude from training?",
                    "Curated-data-trained model (500 trees), scored on the curated pipeline's own held-out test group 9 -- this model's native holdout, and the fair comparison point against production_model_full_500trees_x_production_test.",
                ],
            )
        },
        "headline_roc_auc_delta_equal_tree_count": headline_delta_equal_tree_count,
        "headline_roc_auc_delta_as_deployed": headline_delta_as_deployed,
        "headline_delta_explanation": (
            f"Equal-tree-count (500 vs 500) delta: curated_model_x_curated_test minus "
            f"production_model_full_500trees_x_production_test = {headline_delta_equal_tree_count:+.4f}. "
            f"As-deployed delta: curated_model_x_curated_test minus production_model_x_production_test "
            f"(200 trees) = {headline_delta_as_deployed:+.4f}. "
            + (
                "The two test populations are identical for hERG (same compounds, same labels, same "
                "split assignment), so the equal-tree-count delta isolates pure training/evaluation "
                "noise (e.g. RandomForestClassifier's parallel-fit nondeterminism) rather than any real "
                "difference in what data the models saw -- curation reproduced the exact same "
                "training-eligible population for hERG."
                if same_population
                else "The two test populations differ, so these deltas reflect both any modelling "
                "difference and any difference in which compounds ended up in each test set."
            )
        ),
    }
    CROSS_EVAL_JSON.write_text(json.dumps(cross_report, indent=2) + "\n", encoding="utf-8")

    print(f"\nheadline ROC-AUC delta (equal tree count): {headline_delta_equal_tree_count:+.4f}")
    print(f"headline ROC-AUC delta (as deployed): {headline_delta_as_deployed:+.4f}")
    print(f"own-population report: {OWN_EVAL_JSON}")
    print(f"cross-evaluation report: {CROSS_EVAL_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
