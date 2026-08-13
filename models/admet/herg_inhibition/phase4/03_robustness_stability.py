#!/usr/bin/env python3
"""Phase 4.3: robustness and stability testing.

Read-only with respect to the registered model (never overwrites
artifact/model.joblib). Covers:
  1. Repeated validation across 10 random seeds (same data, same
     hyperparameters, only the RF's internal randomness varies).
  2. Bootstrap perturbation of the training set (resampled with replacement,
     same size, evaluated on the SAME fixed test set) -- a more realistic
     "different training data" stress test than just reseeding the model.
  3. Chemical diversity: scaffold-to-compound ratio, per-split-group class
     balance (does any split group have a pathological class skew from
     scaffold clustering?).
  4. Alternative feature representations: descriptors-only vs.
     fingerprint-only vs. the registered combined representation.
  5. Threshold sensitivity is NOT re-run here -- already covered exhaustively
     in Phase 3.5 (threshold_sensitivity.py); cited, not duplicated.

Usage:
    python models/admet/herg_inhibition/phase4/03_robustness_stability.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[4]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
TRAIN_MANIFEST = ROOT / "models" / "admet" / "herg_inhibition" / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "03_robustness_stability_report.json"

TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9
N_SEED_REPEATS = 10
N_BOOTSTRAP_REPEATS = 10
BASE_SEED = 2000


def _load(data: dict, groups: list[int], which: str = "combined") -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    if which == "combined":
        x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    elif which == "descriptors":
        x = data["descriptors"][mask]
    elif which == "fingerprints":
        x = data["fingerprints"][mask]
    else:
        raise ValueError(which)
    return x, data["labels"][mask]


def main() -> int:
    """Run all robustness/stability checks."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    params = json.loads(TRAIN_MANIFEST.read_text())["hyperparameters"]
    result: dict = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    x_train, y_train = _load(data, TRAIN_GROUPS)
    x_test, y_test = _load(data, [TEST_GROUP])

    # --- 1. Repeated validation across seeds ---
    seed_aucs, seed_bal_accs = [], []
    for i in range(N_SEED_REPEATS):
        seed = BASE_SEED + i
        model = RandomForestClassifier(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            class_weight="balanced", random_state=seed, n_jobs=-1,
        )
        model.fit(x_train, y_train)
        prob = model.predict_proba(x_test)[:, 1]
        seed_aucs.append(roc_auc_score(y_test, prob))
        seed_bal_accs.append(balanced_accuracy_score(y_test, (prob >= 0.5).astype(int)))
    result["seed_repeats"] = {
        "n_repeats": N_SEED_REPEATS,
        "test_roc_auc_mean": round(float(np.mean(seed_aucs)), 4),
        "test_roc_auc_std": round(float(np.std(seed_aucs)), 4),
        "test_roc_auc_min_max": [round(float(min(seed_aucs)), 4), round(float(max(seed_aucs)), 4)],
        "test_balanced_accuracy_mean": round(float(np.mean(seed_bal_accs)), 4),
        "test_balanced_accuracy_std": round(float(np.std(seed_bal_accs)), 4),
        "registered_test_roc_auc": 0.7875,
        "registered_within_1_std": bool(abs(0.7875 - np.mean(seed_aucs)) <= np.std(seed_aucs)),
    }
    print(f"seed repeats: test AUC {np.mean(seed_aucs):.4f} +/- {np.std(seed_aucs):.4f}", file=sys.stderr)

    # --- 2. Bootstrap perturbation of the training set ---
    boot_aucs = []
    rng_master = np.random.default_rng(BASE_SEED + 100)
    for i in range(N_BOOTSTRAP_REPEATS):
        idx = rng_master.integers(0, len(y_train), size=len(y_train))
        x_boot, y_boot = x_train[idx], y_train[idx]
        model = RandomForestClassifier(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            class_weight="balanced", random_state=params.get("random_seed", 42) if isinstance(params, dict) else 42,
            n_jobs=-1,
        )
        model.fit(x_boot, y_boot)
        prob = model.predict_proba(x_test)[:, 1]
        boot_aucs.append(roc_auc_score(y_test, prob))
    result["bootstrap_train_perturbation"] = {
        "n_repeats": N_BOOTSTRAP_REPEATS,
        "test_roc_auc_mean": round(float(np.mean(boot_aucs)), 4),
        "test_roc_auc_std": round(float(np.std(boot_aucs)), 4),
        "test_roc_auc_min_max": [round(float(min(boot_aucs)), 4), round(float(max(boot_aucs)), 4)],
        "interpretation": "measures sensitivity to WHICH training compounds are included, not just RF internal randomness",
    }
    print(f"bootstrap: test AUC {np.mean(boot_aucs):.4f} +/- {np.std(boot_aucs):.4f}", file=sys.stderr)

    # --- 3. Chemical diversity + per-split-group class balance ---
    import csv as csvmod
    with DATASET_CSV.open() as f:
        rows = list(csvmod.DictReader(f))
    n_scaffolds = len({r["bemis_murcko_scaffold"] or r["standardized_smiles"] for r in rows})
    result["chemical_diversity"] = {
        "n_compounds": len(rows),
        "n_distinct_scaffolds": n_scaffolds,
        "scaffold_to_compound_ratio": round(n_scaffolds / len(rows), 4),
        "interpretation": (
            "ratio near 1.0 = highly diverse (mostly singleton scaffolds); near 0 = few scaffolds, many "
            "analogues each -- 0.53 indicates moderate diversity with a substantial fraction of the dataset "
            "in analogue series"
        ),
    }

    group_balance = {}
    for g in range(10):
        mask = data["split_groups"] == g
        labels_g = data["labels"][mask]
        group_balance[str(g)] = {
            "n": int(mask.sum()),
            "positive_fraction": round(float(labels_g.mean()), 4) if mask.sum() > 0 else None,
        }
    fractions = [v["positive_fraction"] for v in group_balance.values()]
    result["per_split_group_class_balance"] = {
        "groups": group_balance,
        "positive_fraction_range": [round(min(fractions), 4), round(max(fractions), 4)],
        "positive_fraction_std_across_groups": round(float(np.std(fractions)), 4),
    }

    # --- 4. Alternative feature representations ---
    feature_variants = {}
    for which in ["descriptors", "fingerprints", "combined"]:
        x_tr, y_tr = _load(data, TRAIN_GROUPS, which)
        x_te, y_te = _load(data, [TEST_GROUP], which)
        model = RandomForestClassifier(
            n_estimators=params["n_estimators"], max_depth=params["max_depth"],
            class_weight="balanced", random_state=42, n_jobs=-1,
        )
        model.fit(x_tr, y_tr)
        prob = model.predict_proba(x_te)[:, 1]
        feature_variants[which] = {
            "n_features": x_tr.shape[1],
            "test_roc_auc": round(float(roc_auc_score(y_te, prob)), 4),
            "test_balanced_accuracy": round(float(balanced_accuracy_score(y_te, (prob >= 0.5).astype(int))), 4),
        }
        print(f"features={which}: test AUC {feature_variants[which]['test_roc_auc']}", file=sys.stderr)
    result["feature_representation_ablation"] = feature_variants

    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
