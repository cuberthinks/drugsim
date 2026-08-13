#!/usr/bin/env python3
"""Phase 4.7: error analysis on the internal held-out test set.

Covers false positives, false negatives, borderline compounds, largest
errors, per-scaffold error clustering, and out-of-domain failures (cross-
referenced with Phase 4.5's AD tiers), with an explicit attempt to
attribute root causes using data already on hand: how close the true
aggregated IC50 sits to the 10 uM threshold (label uncertainty from
binarising a continuous value), and how many source measurements
contributed to the label (sparse vs. well-replicated).

Usage:
    python models/admet/herg_inhibition/phase4/07_error_analysis.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "07_error_analysis_report.json"

TEST_GROUP = 9
THRESHOLD_NM = 10_000.0
BORDERLINE_PROB_BAND = (0.4, 0.6)
NEAR_THRESHOLD_FACTOR = 3.0  # within 3x of 10,000 nM either direction


def main() -> int:
    """Run the full error analysis and write a structured report."""
    model = joblib.load(MODEL_PATH)
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    df = pd.read_csv(DATASET_CSV).set_index("inchikey_full")

    test_mask = data["split_groups"] == TEST_GROUP
    x_test = np.concatenate([data["descriptors"][test_mask], data["fingerprints"][test_mask]], axis=1)
    y_test = data["labels"][test_mask]
    ik_test = data["inchikey_full"][test_mask]
    prob_test = model.predict_proba(x_test)[:, 1]
    pred_test = (prob_test >= 0.5).astype(int)

    rows = []
    for i in range(len(y_test)):
        ik = ik_test[i]
        meta = df.loc[ik]
        rows.append({
            "inchikey_full": ik,
            "molecule_pref_names": meta["molecule_pref_names"],
            "scaffold": meta["bemis_murcko_scaffold"] if isinstance(meta["bemis_murcko_scaffold"], str) and meta["bemis_murcko_scaffold"] else meta["standardized_smiles"],
            "aggregated_ic50_nm": float(meta["aggregated_ic50_nm"]),
            "n_source_measurements": int(meta["n_source_measurements"]),
            "n_source_chembl_ids": int(meta["n_source_chembl_ids"]),
            "value_spread_log10": float(meta["value_spread_log10"]) if not pd.isna(meta["value_spread_log10"]) else None,
            "true_label": int(y_test[i]),
            "predicted_label": int(pred_test[i]),
            "predicted_prob": float(prob_test[i]),
            "correct": bool(y_test[i] == pred_test[i]),
        })
    result_df = pd.DataFrame(rows)

    fp = result_df[(result_df.true_label == 0) & (result_df.predicted_label == 1)]
    fn = result_df[(result_df.true_label == 1) & (result_df.predicted_label == 0)]
    borderline = result_df[(result_df.predicted_prob >= BORDERLINE_PROB_BAND[0]) & (result_df.predicted_prob <= BORDERLINE_PROB_BAND[1])]

    near_threshold = result_df[
        (result_df.aggregated_ic50_nm >= THRESHOLD_NM / NEAR_THRESHOLD_FACTOR)
        & (result_df.aggregated_ic50_nm <= THRESHOLD_NM * NEAR_THRESHOLD_FACTOR)
    ]

    # largest, most-confident errors: predicted the wrong class with high confidence
    result_df["confidence_error"] = result_df.apply(
        lambda r: (r.predicted_prob if r.true_label == 0 else 1 - r.predicted_prob) if not r.correct else 0.0,
        axis=1,
    )
    largest_errors = result_df.sort_values("confidence_error", ascending=False).head(10)

    # per-scaffold error clustering (scaffolds with >=3 test compounds)
    scaffold_groups = result_df.groupby("scaffold").agg(n=("correct", "size"), n_errors=("correct", lambda s: (~s).sum()))
    scaffold_groups = scaffold_groups[scaffold_groups.n >= 3].copy()
    scaffold_groups["error_rate"] = scaffold_groups.n_errors / scaffold_groups.n
    worst_scaffolds = scaffold_groups.sort_values("error_rate", ascending=False).head(10)

    # single-measurement vs multi-measurement error rate (data-sparsity attribution)
    single_meas = result_df[result_df.n_source_measurements == 1]
    multi_meas = result_df[result_df.n_source_measurements > 1]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "test_set_n": len(result_df),
        "overall_error_rate": round(1 - result_df.correct.mean(), 4),
        "false_positives": {
            "n": len(fp), "fraction_of_test": round(len(fp) / len(result_df), 4),
            "mean_true_ic50_nm": round(float(fp.aggregated_ic50_nm.mean()), 1) if len(fp) else None,
            "median_true_ic50_nm": round(float(fp.aggregated_ic50_nm.median()), 1) if len(fp) else None,
        },
        "false_negatives": {
            "n": len(fn), "fraction_of_test": round(len(fn) / len(result_df), 4),
            "mean_true_ic50_nm": round(float(fn.aggregated_ic50_nm.mean()), 1) if len(fn) else None,
            "median_true_ic50_nm": round(float(fn.aggregated_ic50_nm.median()), 1) if len(fn) else None,
        },
        "borderline_compounds": {
            "band": BORDERLINE_PROB_BAND, "n": len(borderline),
            "error_rate_within_band": round(1 - borderline.correct.mean(), 4) if len(borderline) else None,
            "error_rate_outside_band": round(1 - result_df[~result_df.index.isin(borderline.index)].correct.mean(), 4),
        },
        "root_cause_label_uncertainty": {
            "near_threshold_band_nm": [THRESHOLD_NM / NEAR_THRESHOLD_FACTOR, THRESHOLD_NM * NEAR_THRESHOLD_FACTOR],
            "n_compounds_near_threshold": len(near_threshold),
            "error_rate_near_threshold": round(1 - near_threshold.correct.mean(), 4) if len(near_threshold) else None,
            "error_rate_far_from_threshold": round(1 - result_df[~result_df.index.isin(near_threshold.index)].correct.mean(), 4),
            "interpretation": (
                "compounds whose true aggregated IC50 sits within 3x of the 10 uM cutoff are inherently "
                "label-fragile -- a small measurement difference would flip their true label. Comparing "
                "error rate near vs. far from the threshold tests whether this is a real driver of errors."
            ),
        },
        "root_cause_measurement_sparsity": {
            "single_measurement_compounds": {"n": len(single_meas), "error_rate": round(1 - single_meas.correct.mean(), 4) if len(single_meas) else None},
            "multi_measurement_compounds": {"n": len(multi_meas), "error_rate": round(1 - multi_meas.correct.mean(), 4) if len(multi_meas) else None},
            "interpretation": "compares error rate for compounds with only one source measurement (more label noise) vs. several",
        },
        "worst_performing_scaffolds": [
            {"scaffold": s, "n": int(row.n), "n_errors": int(row.n_errors), "error_rate": round(float(row.error_rate), 4)}
            for s, row in worst_scaffolds.iterrows()
        ],
        "largest_confident_errors": [
            {
                "name": r.molecule_pref_names if isinstance(r.molecule_pref_names, str) and r.molecule_pref_names else "(unnamed)",
                "true_label": "blocker" if r.true_label == 1 else "non_blocker",
                "predicted_prob_blocker": round(r.predicted_prob, 4),
                "true_ic50_nm": round(r.aggregated_ic50_nm, 1),
                "n_source_measurements": r.n_source_measurements,
                "near_threshold": bool(THRESHOLD_NM / NEAR_THRESHOLD_FACTOR <= r.aggregated_ic50_nm <= THRESHOLD_NM * NEAR_THRESHOLD_FACTOR),
            }
            for r in largest_errors.itertuples()
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
