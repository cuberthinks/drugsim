"""Scientific Coverage 1: external generalisation, AD stratification, thresholds.

Answers external reviewer feedback #2 ("external/non-training-data performance
has relatively low precision/specificity") with the metric family that the
existing Phase 4.5 tier report does *not* contain.

Phase 4.5 (`models/admet/herg_inhibition/phase4/05_applicability_domain.py`)
already stratifies by max-Tanimoto and reports accuracy / balanced accuracy /
ROC-AUC per tier, and already documents the prevalence-shift confound. It does
NOT report **precision, specificity, recall, MCC or PR-AUC** per tier -- which
is precisely the metric family the reviewers commented on. Ranking quality
(ROC-AUC) and thresholded quality (precision/specificity) are different
questions, and the project currently only answers the first one per tier.

This script reuses Phase 4.5's pool construction verbatim in method (same
model artifact, same external CSV, same label rule, same exact-overlap
exclusion, same tier boundaries) so the numbers are directly comparable to the
existing report rather than a parallel universe.

Outputs `01_external_generalisation_report.json` beside this file, and caches
the built pool so the threshold sweep does not re-run RDKit on ~4k compounds.

No model is trained, retrained or modified here. Read-only analysis.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    matthews_corrcoef,
    roc_auc_score,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint, process_structure  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
RAW_EXTERNAL_CSV = ROOT / "datasets" / "raw" / "pubchem_aid588834_raw.csv"
OUT_DIR = Path(__file__).resolve().parent
OUTPUT_JSON = OUT_DIR / "01_external_generalisation_report.json"
POOL_CACHE = OUT_DIR / ".pool_cache.json"

TEST_GROUP = 9
TRAIN_GROUPS = list(range(7))
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]
# Identical boundaries to Phase 4.5 so tiers are comparable across reports.
TIERS = [
    ("highly_similar", 0.7, 1.01),
    ("moderately_similar", 0.4, 0.7),
    ("chemically_novel", 0.2, 0.4),
    ("out_of_domain", -0.01, 0.2),
]
DEFAULT_THRESHOLD = 0.5
SWEEP = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]


def _max_tanimoto(query_fps: np.ndarray, ref_fps: np.ndarray) -> np.ndarray:
    q, r = query_fps.astype(np.float32), ref_fps.astype(np.float32)
    inter = q @ r.T
    union = q.sum(axis=1, keepdims=True) + r.sum(axis=1, keepdims=True).T - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 0.0)
    return sim.max(axis=1)


def _classification_metrics(labels: np.ndarray, probs: np.ndarray, threshold: float) -> dict:
    """Full thresholded + ranking metric set for one group of compounds.

    Returns ``None``-valued ranking metrics when a group is single-class:
    ROC-AUC and PR-AUC are undefined there, and reporting a fabricated value
    would be worse than reporting the absence.
    """
    pred = (probs >= threshold).astype(int)
    tp = int(((pred == 1) & (labels == 1)).sum())
    fp = int(((pred == 1) & (labels == 0)).sum())
    fn = int(((pred == 0) & (labels == 1)).sum())
    tn = int(((pred == 0) & (labels == 0)).sum())

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    specificity = tn / (tn + fp) if (tn + fp) else None
    both_classes = len(np.unique(labels)) > 1

    return {
        "n": int(len(labels)),
        "positive_fraction": round(float(labels.mean()), 4) if len(labels) else None,
        "threshold": threshold,
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "specificity": round(specificity, 4) if specificity is not None else None,
        "balanced_accuracy": (
            round((recall + specificity) / 2, 4)
            if recall is not None and specificity is not None
            else None
        ),
        "accuracy": round(float((pred == labels).mean()), 4) if len(labels) else None,
        "mcc": round(float(matthews_corrcoef(labels, pred)), 4) if both_classes else None,
        "roc_auc": round(float(roc_auc_score(labels, probs)), 4) if both_classes else None,
        "pr_auc": round(float(average_precision_score(labels, probs)), 4) if both_classes else None,
    }


def _build_pool() -> list[dict]:
    """Build internal-test + external pools. Method identical to Phase 4.5."""
    model = joblib.load(MODEL_PATH)
    train_data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_mask = np.isin(train_data["split_groups"], TRAIN_GROUPS)
    train_fps = train_data["fingerprints"][train_mask]
    train_inchikeys = set(train_data["inchikey_full"][train_mask].tolist())

    pool: list[dict] = []

    # --- internal held-out test set (split group 9) ---
    mask = train_data["split_groups"] == TEST_GROUP
    x = np.concatenate([train_data["descriptors"][mask], train_data["fingerprints"][mask]], axis=1)
    y = train_data["labels"][mask]
    prob = model.predict_proba(x)[:, 1]
    tan = _max_tanimoto(train_data["fingerprints"][mask], train_fps)
    for i in range(int(mask.sum())):
        pool.append({
            "source": "internal_test",
            "label": int(y[i]),
            "prob": float(prob[i]),
            "max_tanimoto": float(tan[i]),
        })

    # --- external PubChem AID 588834 ---
    df = pd.read_csv(RAW_EXTERNAL_CSV, skiprows=[1, 2, 3])
    df["Potency"] = pd.to_numeric(df["Potency"], errors="coerce")
    df = df.sort_values("Potency", na_position="last").drop_duplicates(subset="PUBCHEM_CID", keep="first")
    df = df.dropna(subset=["PUBCHEM_CID", "PUBCHEM_EXT_DATASOURCE_SMILES"])

    for i, row in enumerate(df.itertuples()):
        outcome = row.PUBCHEM_ACTIVITY_OUTCOME
        potency_um = row.Potency
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
            continue  # exact-overlap excluded, matching Phase 4.4/4.5
        mol = parse_molecule(processed.standardized_smiles)
        d = compute_descriptors(mol)
        descriptors = [getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]
        fp = compute_morgan_fingerprint(mol)
        xq = np.concatenate([descriptors, fp]).reshape(1, -1)
        pool.append({
            "source": "external_pubchem",
            "cid": str(row.PUBCHEM_CID),
            "label": label,
            "prob": float(model.predict_proba(xq)[0, 1]),
            "max_tanimoto": float(_max_tanimoto(fp.reshape(1, -1), train_fps)[0]),
        })
        if (i + 1) % 500 == 0:
            print(f"  external processed {i + 1}/{len(df)}", file=sys.stderr)

    return pool


def main() -> int:
    if POOL_CACHE.exists():
        print("Using cached pool.", file=sys.stderr)
        pool = json.loads(POOL_CACHE.read_text())
    else:
        pool = _build_pool()
        POOL_CACHE.write_text(json.dumps(pool))

    ext = [p for p in pool if p["source"] == "external_pubchem"]
    internal = [p for p in pool if p["source"] == "internal_test"]

    def arrs(rows):
        return (
            np.array([r["label"] for r in rows]),
            np.array([r["prob"] for r in rows]),
            np.array([r["max_tanimoto"] for r in rows]),
        )

    ext_y, ext_p, ext_t = arrs(ext)
    int_y, int_p, _ = arrs(internal)

    # --- Section 6/7: external-only, stratified by applicability-domain tier ---
    external_by_tier = {}
    for name, lo, hi in TIERS:
        sel = (ext_t >= lo) & (ext_t < hi)
        if sel.sum() == 0:
            external_by_tier[name] = {"n": 0}
            continue
        m = _classification_metrics(ext_y[sel], ext_p[sel], DEFAULT_THRESHOLD)
        m["tanimoto_range"] = [lo, hi]
        m["mean_tanimoto"] = round(float(ext_t[sel].mean()), 4)
        external_by_tier[name] = m

    # --- Section 8: threshold sensitivity on the external distribution ---
    threshold_sweep = {
        f"{t:.2f}": _classification_metrics(ext_y, ext_p, t) for t in SWEEP
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "hERG inhibition only. Read-only analysis: no model trained, retrained or "
            "modified. Extends Phase 4.5 with the precision/specificity/PR-AUC/MCC "
            "metric family it does not report."
        ),
        "method_provenance": {
            "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
            "external_source": "PubChem AID 588834 (NCATS qHTS hERG screen)",
            "external_csv": str(RAW_EXTERNAL_CSV.relative_to(ROOT)),
            "label_rule": "AC50 <= 10000 nM = blocker; identical to training-set rule",
            "exact_training_overlap": "excluded by full InChIKey, matching Phase 4.4/4.5",
            "tier_boundaries": "identical to Phase 4.5 for cross-report comparability",
            "decision_threshold": DEFAULT_THRESHOLD,
        },
        "pool_composition": {
            "internal_test": len(internal),
            "external_pubchem": len(ext),
        },
        "reference_internal_test": _classification_metrics(int_y, int_p, DEFAULT_THRESHOLD),
        "external_overall": _classification_metrics(ext_y, ext_p, DEFAULT_THRESHOLD),
        "external_by_applicability_domain_tier": external_by_tier,
        "threshold_sensitivity_external": threshold_sweep,
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
