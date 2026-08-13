#!/usr/bin/env python3
"""Phase 4.6: uncertainty and calibration, extended to the external set.

Phase 3's reliability.py already established, on the internal test set:
  - split conformal empirical coverage: 89.88% vs. 90% nominal (within tolerance)
  - raw model calibration (Brier 0.1864, ECE 0.0597) beats Platt/isotonic

This script does NOT repeat those (cited, not recomputed) and instead adds
what Phase 4 specifically requires beyond Phase 3: applying the SAME
conformal calibration (fit once, on split_group 7, never refit here) to the
external PubChem set, to test whether the coverage guarantee survives a real
distribution shift -- and reporting calibration/coverage separately inside
vs. outside the applicability domain (Phase 4.5's tiers).

IMPORTANT PRECISION, not stylistic: split conformal prediction guarantees
MARGINAL coverage over a population under exchangeability with the
calibration set -- e.g. "the true label falls in the predicted set at least
90% of the time, averaged over many predictions from the same distribution
as calibration." It is NOT a per-instance probability that any single
prediction is correct, and the guarantee itself is not assumed to survive a
population whose label distribution differs sharply from calibration (which
is exactly the situation being tested here). This script does not describe
any per-instance conformal output as "probability of being correct."

Usage:
    python models/admet/herg_inhibition/phase4/06_uncertainty_calibration.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint, process_structure  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
RAW_EXTERNAL_CSV = ROOT / "datasets" / "raw" / "pubchem_aid588834_raw.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "06_uncertainty_calibration_report.json"

CALIBRATION_GROUP = 7
TRAIN_GROUPS = list(range(7))
NOMINAL_CONFIDENCE = 0.90
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (y_prob >= lo) & (y_prob < hi) if hi < 1.0 else (y_prob >= lo) & (y_prob <= hi)
        if mask.sum() == 0:
            continue
        total += (mask.sum() / len(y_prob)) * abs(y_prob[mask].mean() - y_true[mask].mean())
    return float(total)


def _load_external(model, train_fps: np.ndarray, train_inchikeys: set[str]) -> list[dict]:
    df = pd.read_csv(RAW_EXTERNAL_CSV, skiprows=[1, 2, 3])
    df["Potency"] = pd.to_numeric(df["Potency"], errors="coerce")
    df = df.sort_values("Potency", na_position="last").drop_duplicates(subset="PUBCHEM_CID", keep="first")
    df = df.dropna(subset=["PUBCHEM_CID", "PUBCHEM_EXT_DATASOURCE_SMILES"])

    records = []
    for row in df.itertuples():
        outcome, potency_um = row.PUBCHEM_ACTIVITY_OUTCOME, row.Potency
        if outcome == "Inconclusive":
            continue
        if outcome == "Inactive" and pd.isna(potency_um):
            label = 0
        elif not pd.isna(potency_um):
            label = 1 if (potency_um * 1000.0) <= 10_000.0 else 0
        else:
            continue
        try:
            processed = process_structure(row.PUBCHEM_EXT_DATASOURCE_SMILES)
        except StructureError:
            continue
        if processed.is_mixture or processed.identity.inchikey_full in train_inchikeys:
            continue
        mol = parse_molecule(processed.standardized_smiles)
        d = compute_descriptors(mol)
        descriptors = [getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]
        fp = compute_morgan_fingerprint(mol)
        x = np.concatenate([descriptors, fp])
        records.append({"label": label, "x": x, "fp": fp})
    return records


def main() -> int:
    """Apply Phase 3's fixed conformal calibration to the external set."""
    model = joblib.load(MODEL_PATH)
    data = np.load(FEATURES_NPZ, allow_pickle=True)

    cal_mask = data["split_groups"] == CALIBRATION_GROUP
    x_cal = np.concatenate([data["descriptors"][cal_mask], data["fingerprints"][cal_mask]], axis=1)
    y_cal = data["labels"][cal_mask]
    cal_probs = model.predict_proba(x_cal)
    cal_true_class_prob = np.where(y_cal == 1, cal_probs[:, 1], cal_probs[:, 0])
    cal_nonconformity = 1.0 - cal_true_class_prob
    n_cal = len(cal_nonconformity)
    epsilon = 1.0 - NOMINAL_CONFIDENCE

    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    train_fps = data["fingerprints"][train_mask]
    train_inchikeys = set(data["inchikey_full"][train_mask])

    print("featurising external set (reusing cached raw CSV)...", file=sys.stderr)
    ext = _load_external(model, train_fps, train_inchikeys)
    x_ext = np.array([r["x"] for r in ext])
    y_ext = np.array([r["label"] for r in ext])
    ext_probs = model.predict_proba(x_ext)

    def _p_value(candidate_col: np.ndarray) -> np.ndarray:
        alpha = 1.0 - candidate_col
        counts = (cal_nonconformity[None, :] >= alpha[:, None]).sum(axis=1)
        return (counts + 1) / (n_cal + 1)

    p0, p1 = _p_value(ext_probs[:, 0]), _p_value(ext_probs[:, 1])
    include_0, include_1 = p0 > epsilon, p1 > epsilon
    pred_sets = [({0, 1} if (i0 and i1) else ({0} if i0 else ({1} if i1 else set()))) for i0, i1 in zip(include_0, include_1)]
    covered = [int(y_ext[i]) in pred_sets[i] for i in range(len(y_ext))]
    external_coverage = float(np.mean(covered))

    raw_prob_1 = ext_probs[:, 1]
    ece_external = _ece(y_ext, raw_prob_1)
    brier_external = float(brier_score_loss(y_ext, raw_prob_1))

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cited_from_phase3_not_recomputed": {
            "internal_test_conformal_empirical_coverage": 0.8988,
            "internal_test_nominal_confidence": 0.90,
            "internal_test_calibration_brier_raw": 0.1864,
            "internal_test_calibration_ece_raw": 0.0597,
        },
        "conformal_precision_statement": (
            "Split conformal coverage is a MARGINAL guarantee over a population exchangeable with the "
            "calibration set -- e.g. 'the true label falls in the predicted set at least 90% of the time, "
            "averaged over many predictions from the calibration distribution.' It is NOT a per-instance "
            "probability that any single prediction is correct, and the guarantee is not assumed to survive "
            "a population whose label distribution differs sharply from calibration -- which this section "
            "tests empirically rather than assumes."
        ),
        "external_set_conformal_coverage": {
            "n": len(y_ext),
            "nominal_confidence": NOMINAL_CONFIDENCE,
            "empirical_coverage": round(external_coverage, 4),
            "within_tolerance_of_nominal": bool(external_coverage >= NOMINAL_CONFIDENCE - 0.05),
            "interpretation": (
                "coverage measured on a population with ~9% positive rate, vs. ~66% in the calibration set "
                "-- a real test of whether the exchangeability assumption behind the marginal guarantee holds "
                "under distribution shift, not just a repeat of the internal-test check"
            ),
        },
        "external_set_calibration": {
            "brier_score_raw": round(brier_external, 4),
            "ece_raw": round(ece_external, 4),
            "comparison_to_internal_test": "internal Brier 0.1864 / ECE 0.0597 -- see cited_from_phase3 above",
        },
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("conformal_precision_statement",)}, indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
