#!/usr/bin/env python3
"""y-scrambling: permute training labels, retrain, confirm collapse to chance.

Required per TDS Sec 6.4: "Permuting labels and retraining must collapse
performance to chance. A model that performs well on scrambled labels is
fitting an artefact -- a leak, a duplicate, or a confounded descriptor."

Uses the SAME algorithm and hyperparameters selected in train.py (Random
Forest with train_manifest.json's winning config), trained on the same
group-0-6 training set with labels permuted, evaluated on the real
validation-group (group 8) labels. Repeated 10 times with different
permutation seeds to report a distribution, not a single lucky/unlucky draw.

Usage:
    python models/admet/herg_inhibition/y_scrambling.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
TRAIN_MANIFEST = Path(__file__).resolve().parent / "train_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "y_scrambling_report.json"

TRAIN_GROUPS = list(range(7))
VALIDATION_GROUP = 8
N_REPEATS = 10
BASE_SEED = 1000


def _load_split(data: dict, groups: list[int]) -> tuple[np.ndarray, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    return x, y


def main() -> int:
    """Run y-scrambling and compare against the real model's performance."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    x_train, y_train = _load_split(data, TRAIN_GROUPS)
    x_val, y_val = _load_split(data, [VALIDATION_GROUP])

    train_manifest = json.loads(TRAIN_MANIFEST.read_text(encoding="utf-8"))
    if train_manifest["algorithm"] != "random_forest":
        msg = (
            f"train_manifest.json selected {train_manifest['algorithm']!r}, but this script "
            "hardcodes RandomForestClassifier -- update it to match before trusting this run"
        )
        raise RuntimeError(msg)
    params = train_manifest["hyperparameters"]

    real_model = RandomForestClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        class_weight="balanced",
        random_state=train_manifest["random_seed"],
        n_jobs=-1,
    )
    real_model.fit(x_train, y_train)
    real_auc = roc_auc_score(y_val, real_model.predict_proba(x_val)[:, 1])
    print(f"real-label model: validation ROC-AUC = {real_auc:.4f}", file=sys.stderr)

    scrambled_aucs = []
    for i in range(N_REPEATS):
        rng = np.random.default_rng(BASE_SEED + i)
        y_scrambled = rng.permutation(y_train)

        model = RandomForestClassifier(
            n_estimators=params["n_estimators"],
            max_depth=params["max_depth"],
            class_weight="balanced",
            random_state=train_manifest["random_seed"],
            n_jobs=-1,
        )
        model.fit(x_train, y_scrambled)
        auc = roc_auc_score(y_val, model.predict_proba(x_val)[:, 1])
        scrambled_aucs.append(auc)
        print(f"  scrambled run {i + 1}/{N_REPEATS}: validation ROC-AUC = {auc:.4f}", file=sys.stderr)

    scrambled_aucs_arr = np.array(scrambled_aucs)
    mean_scrambled = float(scrambled_aucs_arr.mean())
    std_scrambled = float(scrambled_aucs_arr.std())

    # A scrambled model "collapsing to chance" means its AUC distribution is
    # centred near 0.5 and clearly separated from the real model's AUC --
    # not merely "lower". Both conditions are checked explicitly.
    near_chance = bool(abs(mean_scrambled - 0.5) < 0.07)
    clearly_separated = bool((real_auc - mean_scrambled) > 3 * max(std_scrambled, 1e-6))
    collapsed = near_chance and clearly_separated

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "algorithm": train_manifest["algorithm"],
        "hyperparameters": params,
        "n_repeats": N_REPEATS,
        "real_model_validation_roc_auc": round(real_auc, 4),
        "scrambled_validation_roc_auc": {
            "mean": round(mean_scrambled, 4),
            "std": round(std_scrambled, 4),
            "min": round(float(scrambled_aucs_arr.min()), 4),
            "max": round(float(scrambled_aucs_arr.max()), 4),
            "all_runs": [round(a, 4) for a in scrambled_aucs],
        },
        "near_chance_threshold": "abs(mean_scrambled - 0.5) < 0.07",
        "near_chance": near_chance,
        "clearly_separated_threshold": "real_auc - mean_scrambled > 3*std_scrambled",
        "clearly_separated": clearly_separated,
        "status": "PASS (collapsed to chance)" if collapsed else "FAIL (did not collapse -- investigate for leakage/artifact)",
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    print(f"\nreal AUC: {real_auc:.4f}; scrambled AUC: {mean_scrambled:.4f} +/- {std_scrambled:.4f}")
    print(f"status: {result['status']}")
    print(f"report: {OUTPUT_JSON}")
    return 0 if collapsed else 1


if __name__ == "__main__":
    sys.exit(main())
