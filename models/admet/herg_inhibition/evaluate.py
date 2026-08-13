#!/usr/bin/env python3
"""Evaluate on the held-out test group -- touched exactly once, here.

Dual-split reporting per TDS Sec 6.4.1 / data contract (docs/tds/04-data-
contracts.md): both a "global_split" (honest, leakage-controlled) and a
"benchmark_split" number must be published, with a gap_explanation.

Limitation, stated plainly rather than glossed over: TDS Sec 6.4.1 assumes
a TDC canonical split exists for benchmark-comparability. This dataset was
built directly from ChEMBL (Sec 1 of this report explains why -- TDC's own
download endpoint is blocked from this environment), not via TDC, so no
literal TDC-canonical split exists for these exact 9,589 compounds. A
random-split proxy is reported instead of a true TDC benchmark number: same
data, same model, same procedure, but compounds are assigned to train/test
uniformly at random rather than by scaffold. This demonstrates the same
phenomenon ADR-009 exists to guard against (a naive split reports an
inflated, leakage-optimistic number) without overstating it as a genuine
leaderboard comparison.

Usage:
    python models/admet/herg_inhibition/evaluate.py
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
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "evaluation_report.json"

TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9
RANDOM_SPLIT_SEED = 42
RANDOM_SPLIT_TEST_FRACTION = 800 / 9589  # match the global split's test size exactly


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
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
    """Evaluate the champion model on the untouched test group, once."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    model = joblib.load(MODEL_PATH)

    # -- Global (scaffold) split: the honest number. Group 9, touched here
    # for the first and only time in this pipeline. --
    x_test, y_test = _load_split(data, [TEST_GROUP])
    y_prob_global = model.predict_proba(x_test)[:, 1]
    global_metrics = _binary_metrics(y_test, y_prob_global)
    print(f"global (scaffold) split test ROC-AUC: {global_metrics['roc_auc']:.4f}", file=sys.stderr)

    # -- Benchmark-proxy: random split of the SAME full dataset, same model
    # config, retrained fresh (this is a different train set than the global
    # split's groups 0-6, by design -- that is the entire point of the
    # comparison). --
    x_all = np.concatenate([data["descriptors"], data["fingerprints"]], axis=1)
    y_all = data["labels"]
    x_tr, x_te, y_tr, y_te = train_test_split(
        x_all, y_all, test_size=RANDOM_SPLIT_TEST_FRACTION, random_state=RANDOM_SPLIT_SEED, stratify=y_all
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
            "description": "Scaffold-level split_group 9, per ADR-009. Touched once, here.",
        },
        "benchmark_split": {
            **benchmark_metrics,
            "description": (
                "Random-split PROXY, not a true TDC canonical benchmark split -- no TDC split exists "
                "for this exact ChEMBL-sourced compound set (see module docstring). Same model config, "
                "same data pool, same test fraction, stratified random assignment instead of scaffold."
            ),
        },
        "roc_auc_gap": gap,
        "gap_explanation": (
            "Global scaffold splitting prevents cross-dataset/near-neighbour leakage; the random-split "
            "proxy is optimistic because structurally near-identical compounds (same scaffold, minor "
            "substituent changes) can appear in both its train and test sets. The "
            f"{gap:+.4f} ROC-AUC gap is the leakage the scaffold split is removing, not a property of "
            "the model changing between the two runs."
        ),
        "limitation": (
            "This is not a TDC-comparable leaderboard number -- it is a within-dataset random-vs-scaffold "
            "ablation on the same ChEMBL-sourced compounds, included because a true external benchmark "
            "split does not exist for this dataset (Sec 1 of the Phase 3 report explains why TDC itself "
            "was not used as the data source)."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nROC-AUC gap (benchmark-proxy minus global): {gap:+.4f}")
    print(f"report: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
