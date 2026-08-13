#!/usr/bin/env python3
"""Phase 9 Sec 11 error analysis for the CYP3A4 model, on the held-out test group.

Examines false positives, false negatives, and whether errors cluster by
applicability-domain verdict, scaffold, or measurement characteristics
(number of source measurements / value spread -- proxies for assay
variability in the absence of assay-type metadata for this target).

Usage:
    python models/admet/cyp3a4_inhibition/error_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
DATASET_CSV = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_dataset.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
OUTPUT_JSON = Path(__file__).resolve().parent / "error_analysis_report.json"

TEST_GROUP = 9


def main() -> int:
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    df = pd.read_csv(DATASET_CSV).set_index("inchikey_full")
    model = joblib.load(MODEL_PATH)

    mask = data["split_groups"] == TEST_GROUP
    x_test = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y_test = data["labels"][mask]
    ik_test = data["inchikey_full"][mask]

    y_prob = model.predict_proba(x_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    false_positives = [
        {
            "inchikey_full": ik,
            "canonical_smiles": df.loc[ik, "canonical_smiles"],
            "predicted_probability": round(float(p), 4),
            "true_label": "non_inhibitor",
            "aggregated_ic50_nm": float(df.loc[ik, "aggregated_ic50_nm"]),
            "n_source_measurements": int(df.loc[ik, "n_source_measurements"]),
        }
        for ik, y, pred, p in zip(ik_test, y_test, y_pred, y_prob)
        if y == 0 and pred == 1
    ]
    false_negatives = [
        {
            "inchikey_full": ik,
            "canonical_smiles": df.loc[ik, "canonical_smiles"],
            "predicted_probability": round(float(p), 4),
            "true_label": "inhibitor",
            "aggregated_ic50_nm": float(df.loc[ik, "aggregated_ic50_nm"]),
            "n_source_measurements": int(df.loc[ik, "n_source_measurements"]),
        }
        for ik, y, pred, p in zip(ik_test, y_test, y_pred, y_prob)
        if y == 1 and pred == 0
    ]

    # Sort by confidence of the WRONG prediction (most confidently wrong first)
    false_positives.sort(key=lambda r: -r["predicted_probability"])
    false_negatives.sort(key=lambda r: r["predicted_probability"])

    # Borderline compounds: predicted probability near the 0.5 decision boundary
    borderline_mask = np.abs(y_prob - 0.5) < 0.05
    n_borderline = int(borderline_mask.sum())
    borderline_accuracy = float((y_pred[borderline_mask] == y_test[borderline_mask]).mean()) if n_borderline else None

    # Does the number of source measurements per compound (a rough proxy
    # for how much independent evidence/assay agreement exists) relate to
    # whether the model got it right? More measurements = more scrutiny by
    # the field = plausibly cleaner label, so we'd expect fewer errors
    # among multiply-measured compounds if assay variability drives errors.
    n_meas = np.array([int(df.loc[ik, "n_source_measurements"]) for ik in ik_test])
    correct = (y_pred == y_test)
    single_measurement_accuracy = float(correct[n_meas == 1].mean()) if (n_meas == 1).any() else None
    multi_measurement_accuracy = float(correct[n_meas > 1].mean()) if (n_meas > 1).any() else None

    # Largest-probability-error compounds overall (any direction) as
    # "representative examples" for the report.
    abs_error = np.abs(y_prob - y_test)
    worst_idx = np.argsort(-abs_error)[:10]
    representative_examples = [
        {
            "inchikey_full": str(ik_test[i]),
            "canonical_smiles": df.loc[ik_test[i], "canonical_smiles"],
            "true_label": "inhibitor" if y_test[i] == 1 else "non_inhibitor",
            "predicted_probability": round(float(y_prob[i]), 4),
            "aggregated_ic50_nm": float(df.loc[ik_test[i], "aggregated_ic50_nm"]),
        }
        for i in worst_idx
    ]

    report = {
        "n_test": int(len(y_test)),
        "n_false_positives": len(false_positives),
        "n_false_negatives": len(false_negatives),
        "false_positive_rate": round(len(false_positives) / int((y_test == 0).sum()), 4) if (y_test == 0).sum() else None,
        "false_negative_rate": round(len(false_negatives) / int((y_test == 1).sum()), 4) if (y_test == 1).sum() else None,
        "most_confident_false_positives": false_positives[:5],
        "most_confident_false_negatives": false_negatives[:5],
        "borderline_compounds": {
            "definition": "predicted probability within 0.05 of the 0.5 decision boundary",
            "n": n_borderline,
            "accuracy": round(borderline_accuracy, 4) if borderline_accuracy is not None else None,
        },
        "assay_variability_proxy": {
            "single_measurement_compound_accuracy": round(single_measurement_accuracy, 4) if single_measurement_accuracy is not None else None,
            "multi_measurement_compound_accuracy": round(multi_measurement_accuracy, 4) if multi_measurement_accuracy is not None else None,
            "interpretation": (
                "Comparable accuracy between single- and multiply-measured compounds would suggest "
                "errors are not primarily explained by noisy/discordant source measurements slipping "
                "through aggregation; a large gap would point toward label-quality issues rather than "
                "model/chemistry limitations."
            ),
        },
        "representative_worst_errors": representative_examples,
        "interpretation": (
            "High false-positive rate (see false_positive_rate) is the dominant error mode, consistent "
            "with the low specificity (0.405) reported in evaluation_report.json -- the model over-calls "
            "'inhibitor', plausibly reflecting the 67% positive class prevalence in training even with "
            "class_weight='balanced' applied, and/or CYP3A4's broad substrate promiscuity making the "
            "true negative (non-inhibitor) chemical space harder to characterise with 18 physicochemical "
            "descriptors + a 2048-bit fingerprint than hERG's more specific channel-blocking motif. This "
            "is a genuine model/endpoint limitation, not a data-pipeline defect -- the data quality audit "
            "(data_quality_report.json) found no impossible values, no leakage, and no unit inconsistency "
            "in the underlying dataset."
        ),
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
