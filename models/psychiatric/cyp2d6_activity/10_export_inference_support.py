#!/usr/bin/env python3
"""Export frozen conformal calibration + applicability-domain reference
data needed at inference time for CYP2D6, as one versioned artifact.

Mirrors ``models/admet/cyp3a4_inhibition/10_export_inference_support.py``
exactly -- this is what makes CYP2D6 loadable through the SAME generic,
already-production `drugsim_predict.model_registry`/`pipeline.run_inference`
machinery hERG and CYP3A4 already use, rather than a bespoke serving
path. NOT a new computation -- packages exactly the reference data this
endpoint's own evaluate.py already validated.

Usage:
    python models/psychiatric/cyp2d6_activity/10_export_inference_support.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = ROOT / "models" / "psychiatric" / "cyp2d6_activity" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp2d6_activity_features.npz"
DATASET_CSV = ROOT / "datasets" / "processed" / "cyp2d6_activity_dataset.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
OUTPUT_NPZ = ARTIFACT_DIR / "inference_support.npz"
OUTPUT_SCALER = ARTIFACT_DIR / "descriptor_ad_scaler.joblib"
OUTPUT_MANIFEST = Path(__file__).resolve().parent / "inference_support_manifest.json"

TRAIN_GROUPS = list(range(7))
CALIBRATION_GROUP = 7
K_NEIGHBOURS = 5
NOMINAL_CONFIDENCE = 0.90


def main() -> int:
    """Build and persist the inference-support artifact."""
    model = joblib.load(MODEL_PATH)
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    df = pd.read_csv(DATASET_CSV)

    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    cal_mask = data["split_groups"] == CALIBRATION_GROUP

    train_descriptors = data["descriptors"][train_mask]
    train_fingerprints = data["fingerprints"][train_mask]
    train_inchikeys = data["inchikey_full"][train_mask]

    x_cal = np.concatenate([data["descriptors"][cal_mask], data["fingerprints"][cal_mask]], axis=1)
    y_cal = data["labels"][cal_mask]
    cal_probs = model.predict_proba(x_cal)
    cal_true_class_prob = np.where(y_cal == 1, cal_probs[:, 1], cal_probs[:, 0])
    calibration_nonconformity = 1.0 - cal_true_class_prob

    scaler = StandardScaler().fit(train_descriptors)
    train_descriptors_scaled = scaler.transform(train_descriptors)

    nn = NearestNeighbors(n_neighbors=K_NEIGHBOURS + 1).fit(train_descriptors_scaled)
    train_nn_dists, _ = nn.kneighbors(train_descriptors_scaled)
    train_internal_dists = train_nn_dists[:, 1:].mean(axis=1)
    knn_threshold = float(np.percentile(train_internal_dists, 95))

    ik_to_scaffold = dict(zip(df["inchikey_full"], df["bemis_murcko_scaffold"].fillna(df["standardized_smiles"])))
    train_scaffolds = sorted({ik_to_scaffold[ik] for ik in train_inchikeys})

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTPUT_NPZ,
        calibration_nonconformity=calibration_nonconformity,
        train_fingerprints=train_fingerprints,
        train_descriptors=train_descriptors,
        train_scaffolds=np.array(train_scaffolds, dtype=object),
    )
    joblib.dump(scaler, OUTPUT_SCALER)

    npz_bytes = OUTPUT_NPZ.read_bytes()
    scaler_bytes = OUTPUT_SCALER.read_bytes()
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_model_sha256": hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest(),
        "n_calibration": int(cal_mask.sum()),
        "n_train": int(train_mask.sum()),
        "n_train_scaffolds": len(train_scaffolds),
        "nominal_confidence": NOMINAL_CONFIDENCE,
        "knn_k": K_NEIGHBOURS,
        "knn_distance_threshold_p95": round(knn_threshold, 6),
        "output_npz": str(OUTPUT_NPZ.relative_to(ROOT)),
        "output_npz_sha256": hashlib.sha256(npz_bytes).hexdigest(),
        "output_scaler": str(OUTPUT_SCALER.relative_to(ROOT)),
        "output_scaler_sha256": hashlib.sha256(scaler_bytes).hexdigest(),
        "note": "Frozen from the SAME calibration/train split used in evaluate.py. Never recomputed at inference time.",
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUTPUT_NPZ} and {OUTPUT_SCALER}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
