#!/usr/bin/env python3
"""Reliability layer for CYP3A4: split conformal prediction, calibration, AD.

Mirrors ``models/admet/herg_inhibition/reliability.py`` exactly -- same
split-conformal procedure, same Platt/isotonic post-hoc calibration
comparison, same three-signal applicability-domain verdict logic
(max Tanimoto + k-NN descriptor distance + scaffold-seen), computed fresh
against THIS endpoint's own calibration/train/test groups.

Usage:
    python models/admet/cyp3a4_inhibition/reliability.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
OUTPUT_JSON = Path(__file__).resolve().parent / "reliability_report.json"

TRAIN_GROUPS = list(range(7))
CALIBRATION_GROUP = 7
TEST_GROUP = 9
NOMINAL_CONFIDENCE = 0.90
K_NEIGHBOURS = 5


def _load_split(data: dict, groups: list[int]) -> dict[str, np.ndarray]:
    mask = np.isin(data["split_groups"], groups)
    return {
        "x": np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1),
        "descriptors": data["descriptors"][mask],
        "fingerprints": data["fingerprints"][mask],
        "y": data["labels"][mask],
        "inchikey_full": data["inchikey_full"][mask],
    }


def _tanimoto_max(query_fps: np.ndarray, reference_fps: np.ndarray) -> np.ndarray:
    q = query_fps.astype(np.float32)
    r = reference_fps.astype(np.float32)
    intersection = q @ r.T
    q_sum = q.sum(axis=1, keepdims=True)
    r_sum = r.sum(axis=1, keepdims=True)
    union = q_sum + r_sum.T - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, intersection / union, 0.0)
    return sim.max(axis=1)


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (y_prob >= lo) & (y_prob < hi) if hi < 1.0 else (y_prob >= lo) & (y_prob <= hi)
        if mask.sum() == 0:
            continue
        bin_conf = y_prob[mask].mean()
        bin_acc = y_true[mask].mean()
        ece += (mask.sum() / len(y_prob)) * abs(bin_conf - bin_acc)
    return float(ece)


def main() -> int:
    """Run conformal prediction, calibration, and AD assessment."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    model = joblib.load(MODEL_PATH)

    train = _load_split(data, TRAIN_GROUPS)
    cal = _load_split(data, [CALIBRATION_GROUP])
    test = _load_split(data, [TEST_GROUP])
    print(f"train={len(train['y'])} calibration={len(cal['y'])} test={len(test['y'])}", file=sys.stderr)

    # --- 1. Split conformal prediction ---
    cal_probs = model.predict_proba(cal["x"])
    cal_true_class_prob = np.where(cal["y"] == 1, cal_probs[:, 1], cal_probs[:, 0])
    cal_nonconformity = 1.0 - cal_true_class_prob

    test_probs = model.predict_proba(test["x"])
    epsilon = 1.0 - NOMINAL_CONFIDENCE
    n_cal = len(cal_nonconformity)

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

    # Singleton reliability: among test compounds where the conformal set
    # narrowed to one class, does that class actually match the true
    # label more often than for the "genuinely uncertain" (both-class) set?
    # This is the concrete "uncertainty vs actual error" check Sec 10 asks for.
    singleton_mask = np.array(set_sizes) == 1
    singleton_correct = [
        (list(prediction_sets[i])[0] == int(test["y"][i])) for i in range(len(test["y"])) if singleton_mask[i]
    ]
    uncertain_mask = np.array(set_sizes) == 2
    y_pred_raw = (test_probs[:, 1] >= 0.5).astype(int)
    uncertain_correct = [
        (y_pred_raw[i] == int(test["y"][i])) for i in range(len(test["y"])) if uncertain_mask[i]
    ]

    conformal_result = {
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
        "uncertainty_tracks_error": (
            (round(float(np.mean(singleton_correct)), 4) if singleton_correct else 0)
            > (round(float(np.mean(uncertain_correct)), 4) if uncertain_correct else 1)
        ),
    }
    print(f"conformal empirical coverage: {empirical_coverage:.4f} (nominal {NOMINAL_CONFIDENCE})", file=sys.stderr)
    print(f"accuracy when singleton: {conformal_result['accuracy_when_singleton']}, when uncertain: {conformal_result['accuracy_when_uncertain_both_classes']}", file=sys.stderr)

    # --- 2. Post-hoc calibration ---
    raw_test_prob = test_probs[:, 1]
    raw_cal_prob = cal_probs[:, 1]

    platt = LogisticRegression()
    platt.fit(raw_cal_prob.reshape(-1, 1), cal["y"])
    platt_test_prob = platt.predict_proba(raw_test_prob.reshape(-1, 1))[:, 1]

    isotonic = IsotonicRegression(out_of_bounds="clip")
    isotonic.fit(raw_cal_prob, cal["y"])
    isotonic_test_prob = isotonic.predict(raw_test_prob)

    calibration_result = {
        "brier_score_raw": round(float(brier_score_loss(test["y"], raw_test_prob)), 4),
        "brier_score_platt": round(float(brier_score_loss(test["y"], platt_test_prob)), 4),
        "brier_score_isotonic": round(float(brier_score_loss(test["y"], isotonic_test_prob)), 4),
        "ece_raw": round(_ece(test["y"], raw_test_prob), 4),
        "ece_platt": round(_ece(test["y"], platt_test_prob), 4),
        "ece_isotonic": round(_ece(test["y"], isotonic_test_prob), 4),
        "reliability_curve_raw": {
            "note": "sklearn calibration_curve, 10 quantile bins",
            **dict(
                zip(
                    ["fraction_of_positives", "mean_predicted_value"],
                    [a.tolist() for a in calibration_curve(test["y"], raw_test_prob, n_bins=10, strategy="quantile")],
                )
            ),
        },
    }
    print(f"Brier: raw={calibration_result['brier_score_raw']} platt={calibration_result['brier_score_platt']} iso={calibration_result['brier_score_isotonic']}", file=sys.stderr)

    # --- 3. Applicability domain ---
    desc_scaler = StandardScaler().fit(train["descriptors"])
    train_desc_scaled = desc_scaler.transform(train["descriptors"])
    test_desc_scaled = desc_scaler.transform(test["descriptors"])

    nn = NearestNeighbors(n_neighbors=K_NEIGHBOURS).fit(train_desc_scaled)
    train_nn_dists, _ = nn.kneighbors(train_desc_scaled, n_neighbors=K_NEIGHBOURS + 1)
    train_internal_dists = train_nn_dists[:, 1:].mean(axis=1)
    knn_threshold = float(np.percentile(train_internal_dists, 95))

    test_nn_dists, _ = nn.kneighbors(test_desc_scaled, n_neighbors=K_NEIGHBOURS)
    test_knn_dist = test_nn_dists.mean(axis=1)

    max_tanimoto = _tanimoto_max(test["fingerprints"], train["fingerprints"])

    import pandas as pd

    df = pd.read_csv(ROOT / "datasets" / "processed" / "cyp3a4_inhibition_dataset.csv")
    ik_to_scaffold = dict(zip(df["inchikey_full"], df["bemis_murcko_scaffold"]))
    train_scaffolds = {ik_to_scaffold.get(ik) for ik in train["inchikey_full"]}
    test_scaffold_seen = np.array(
        [ik_to_scaffold.get(ik) in train_scaffolds for ik in test["inchikey_full"]]
    )

    verdicts = []
    for tanimoto, knn_dist, scaffold_seen in zip(max_tanimoto, test_knn_dist, test_scaffold_seen):
        knn_triggered = knn_dist > knn_threshold
        tanimoto_weak = tanimoto < 0.6
        scaffold_triggered = not scaffold_seen
        n_triggered = sum([tanimoto_weak, knn_triggered, scaffold_triggered])
        if tanimoto < 0.4:
            verdicts.append("out_of_domain")
        elif n_triggered >= 2:
            verdicts.append("out_of_domain")
        elif n_triggered == 1:
            verdicts.append("borderline")
        else:
            verdicts.append("in_domain")

    verdicts = np.array(verdicts)
    y_pred_test = (raw_test_prob >= 0.5).astype(int)
    accuracy_by_verdict = {}
    for v in ["in_domain", "borderline", "out_of_domain"]:
        mask = verdicts == v
        if mask.sum() > 0:
            accuracy_by_verdict[v] = {
                "n": int(mask.sum()),
                "accuracy": round(float((y_pred_test[mask] == test["y"][mask]).mean()), 4),
                "mean_max_tanimoto": round(float(max_tanimoto[mask].mean()), 4),
            }

    # Same structural note as hERG's reliability.py: a scaffold-split test
    # set guarantees scaffold_not_in_training=True for every test compound,
    # so "in_domain" (all 3 signals clear) is mathematically unreachable
    # here by construction. A supplementary 2-signal verdict (Tanimoto +
    # k-NN only) is also computed for the same reason.
    verdicts_2signal = []
    for tanimoto, knn_dist in zip(max_tanimoto, test_knn_dist):
        knn_triggered = knn_dist > knn_threshold
        tanimoto_weak = tanimoto < 0.6
        n_triggered = sum([tanimoto_weak, knn_triggered])
        if tanimoto < 0.4:
            verdicts_2signal.append("out_of_domain")
        elif n_triggered >= 2:
            verdicts_2signal.append("out_of_domain")
        elif n_triggered == 1:
            verdicts_2signal.append("borderline")
        else:
            verdicts_2signal.append("in_domain")
    verdicts_2signal = np.array(verdicts_2signal)
    accuracy_by_verdict_2signal = {}
    for v in ["in_domain", "borderline", "out_of_domain"]:
        mask = verdicts_2signal == v
        if mask.sum() > 0:
            accuracy_by_verdict_2signal[v] = {
                "n": int(mask.sum()),
                "accuracy": round(float((y_pred_test[mask] == test["y"][mask]).mean()), 4),
            }

    ad_result = {
        "knn_k": K_NEIGHBOURS,
        "knn_distance_threshold_p95_of_training": round(knn_threshold, 4),
        "three_signal_verdict_counts": {v: int((verdicts == v).sum()) for v in ["in_domain", "borderline", "out_of_domain"]},
        "three_signal_accuracy_by_verdict": accuracy_by_verdict,
        "three_signal_caveat": (
            "in_domain is 0 here BY CONSTRUCTION (same structural artefact as hERG's own reliability "
            "report): the scaffold-split test set guarantees scaffold_not_in_training=True for every "
            "test compound, which alone contributes one of the up-to-3 triggers this verdict logic "
            "requires to hit zero for in_domain."
        ),
        "two_signal_verdict_counts_scaffold_excluded": {v: int((verdicts_2signal == v).sum()) for v in ["in_domain", "borderline", "out_of_domain"]},
        "two_signal_accuracy_by_verdict": accuracy_by_verdict_2signal,
        "verdict_logic": (
            "out_of_domain if max_tanimoto<0.4 OR >=2 of {max_tanimoto<0.6, knn_dist>p95_train, "
            "scaffold_not_in_training} triggered; borderline if exactly 1 triggered; else in_domain."
        ),
        "reliability_decreases_appropriately_out_of_domain": None,  # filled below
    }
    # Phase 9 Sec 9 explicit check: does accuracy actually degrade moving
    # from more-similar to less-similar chemistry? Uses the informative
    # 2-signal verdict since 3-signal in_domain is empty by construction here.
    two_sig_acc = {k: v["accuracy"] for k, v in accuracy_by_verdict_2signal.items()}
    if "in_domain" in two_sig_acc and "out_of_domain" in two_sig_acc:
        ad_result["reliability_decreases_appropriately_out_of_domain"] = bool(
            two_sig_acc["in_domain"] >= two_sig_acc.get("borderline", two_sig_acc["in_domain"]) >= two_sig_acc["out_of_domain"]
        )
    print(f"AD verdicts (3-signal): {ad_result['three_signal_verdict_counts']}", file=sys.stderr)
    print(f"AD verdicts (2-signal, scaffold excluded): {ad_result['two_signal_verdict_counts_scaffold_excluded']}", file=sys.stderr)
    print(f"2-signal accuracy by verdict: {two_sig_acc}", file=sys.stderr)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "conformal_prediction": conformal_result,
        "calibration": calibration_result,
        "applicability_domain": ad_result,
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
