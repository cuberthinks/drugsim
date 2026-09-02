#!/usr/bin/env python3
"""Export a compact inference-support artifact for HRH1, for live serving.

Unlike CYP2D6/BBB (classification, reusing drugsim_predict's existing
ModelBundle/conformal/AD machinery), HRH1 is a regression endpoint with
no equivalent production infrastructure yet -- this script instead
produces the minimal artifact `screening_profile.py`'s own AD check
actually needs (training-split Morgan fingerprints only), rather than
shipping the full `datasets/processed/hrh1_activity_features.npz`
(which also carries descriptors/labels/local_compound_id for the
WHOLE dataset, not just the training split, and is not meant to be a
serving artifact) into the live Docker image.

The conformal interval half-width and Tanimoto threshold are already
frozen in evaluation_report.json and read directly from there at
serving time -- not duplicated here.

Usage:
    python models/psychiatric/hrh1_activity/10_export_inference_support.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
FEATURES_NPZ = ROOT / "datasets" / "processed" / "hrh1_activity_features.npz"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
OUTPUT_NPZ = ARTIFACT_DIR / "inference_support.npz"
OUTPUT_MANIFEST = Path(__file__).resolve().parent / "inference_support_manifest.json"

TRAIN_GROUPS = list(range(7))


def main() -> int:
    """Build and persist the compact inference-support artifact."""
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    train_fingerprints = data["fingerprints"][train_mask]

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUTPUT_NPZ, train_fingerprints=train_fingerprints)

    npz_bytes = OUTPUT_NPZ.read_bytes()
    manifest = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_train": int(train_mask.sum()),
        "output_npz": str(OUTPUT_NPZ.relative_to(ROOT)),
        "output_npz_sha256": hashlib.sha256(npz_bytes).hexdigest(),
        "note": (
            "Training-split Morgan fingerprints only, for the Tanimoto applicability-domain check "
            "screening_profile.py runs at serving time. Conformal interval half-width and the "
            "Tanimoto in-domain threshold are read directly from evaluation_report.json, not "
            "duplicated here -- both are already frozen from the same train/calibration split."
        ),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {OUTPUT_NPZ} ({train_fingerprints.shape[0]} training fingerprints)")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
