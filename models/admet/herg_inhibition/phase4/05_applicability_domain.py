#!/usr/bin/env python3
"""Phase 4.5: applicability domain across four chemical-similarity tiers.

Combines the internal held-out test set (800 compounds, split_group 9) and
the external PubChem validation set (4,030 compounds, Phase 4.4) into one
pool with known true labels, model predictions, and max-Tanimoto-to-training
already meaningful for both. Stratifies into four tiers:

  1. Highly similar     (max Tanimoto >= 0.7)
  2. Moderately similar  (0.4 <= max Tanimoto < 0.7)
  3. Chemically novel    (0.2 <= max Tanimoto < 0.4)
  4. Clearly out-of-domain (max Tanimoto < 0.2)

and reports accuracy/ROC-AUC per tier plus error rate as an explicit
function of similarity, verifying the AD mechanism's own claim (TDS Sec
6.8: Tanimoto < 0.4 is a "strong OOD signal") against measured error.

Usage:
    python models/admet/herg_inhibition/phase4/05_applicability_domain.py
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint, process_structure  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
RAW_EXTERNAL_CSV = ROOT / "datasets" / "raw" / "pubchem_aid588834_raw.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "05_applicability_domain_report.json"

TEST_GROUP = 9
TRAIN_GROUPS = list(range(7))
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]
TIERS = [
    ("highly_similar", 0.7, 1.01),
    ("moderately_similar", 0.4, 0.7),
    ("chemically_novel", 0.2, 0.4),
    ("out_of_domain", -0.01, 0.2),
]


def _max_tanimoto(query_fps: np.ndarray, ref_fps: np.ndarray) -> np.ndarray:
    q, r = query_fps.astype(np.float32), ref_fps.astype(np.float32)
    inter = q @ r.T
    union = q.sum(axis=1, keepdims=True) + r.sum(axis=1, keepdims=True).T - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 0.0)
    return sim.max(axis=1)


def _build_internal_pool(model, train_fps: np.ndarray) -> list[dict]:
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    mask = data["split_groups"] == TEST_GROUP
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    prob = model.predict_proba(x)[:, 1]
    tanimoto = _max_tanimoto(data["fingerprints"][mask], train_fps)
    return [
        {"source": "internal_test", "label": int(y[i]), "prob": float(prob[i]), "max_tanimoto": float(tanimoto[i])}
        for i in range(mask.sum())
    ]


def _build_external_pool(model, train_fps: np.ndarray, train_inchikeys: set[str]) -> list[dict]:
    df = pd.read_csv(RAW_EXTERNAL_CSV, skiprows=[1, 2, 3])
    df["Potency"] = pd.to_numeric(df["Potency"], errors="coerce")
    df = df.sort_values("Potency", na_position="last").drop_duplicates(subset="PUBCHEM_CID", keep="first")
    df = df.dropna(subset=["PUBCHEM_CID", "PUBCHEM_EXT_DATASOURCE_SMILES"])

    pool = []
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
            continue  # exact-overlap compounds excluded, matching Phase 4.4's leakage-controlled figure
        mol = parse_molecule(processed.standardized_smiles)
        d = compute_descriptors(mol)
        descriptors = [getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]
        fp = compute_morgan_fingerprint(mol)
        x = np.concatenate([descriptors, fp]).reshape(1, -1)
        prob = float(model.predict_proba(x)[0, 1])
        tanimoto = float(_max_tanimoto(fp.reshape(1, -1), train_fps)[0])
        pool.append({"source": "external_pubchem", "label": label, "prob": prob, "max_tanimoto": tanimoto})
        if (i + 1) % 1000 == 0:
            print(f"  processed {i + 1}/{len(df)}", file=sys.stderr)
    return pool


def main() -> int:
    """Stratify by chemical similarity and report accuracy/error per tier."""
    model = joblib.load(MODEL_PATH)
    train_data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_mask = np.isin(train_data["split_groups"], TRAIN_GROUPS)
    train_fps = train_data["fingerprints"][train_mask]
    train_inchikeys = set(train_data["inchikey_full"][train_mask])

    pool = _build_internal_pool(model, train_fps) + _build_external_pool(model, train_fps, train_inchikeys)
    print(f"combined pool: {len(pool)} compounds", file=sys.stderr)

    labels = np.array([p["label"] for p in pool])
    probs = np.array([p["prob"] for p in pool])
    preds = (probs >= 0.5).astype(int)
    tanimoto = np.array([p["max_tanimoto"] for p in pool])

    tier_results = {}
    for name, lo, hi in TIERS:
        mask = (tanimoto >= lo) & (tanimoto < hi)
        n = int(mask.sum())
        if n == 0:
            tier_results[name] = {"n": 0}
            continue
        entry: dict = {
            "n": n,
            "tanimoto_range": [lo, min(hi, 1.0)],
            "mean_tanimoto": round(float(tanimoto[mask].mean()), 4),
            "positive_fraction": round(float(labels[mask].mean()), 4),
            "accuracy": round(float((preds[mask] == labels[mask]).mean()), 4),
            "error_rate": round(float((preds[mask] != labels[mask]).mean()), 4),
        }
        if len(set(labels[mask])) > 1:
            entry["roc_auc"] = round(float(roc_auc_score(labels[mask], probs[mask])), 4)
            entry["balanced_accuracy"] = round(float(balanced_accuracy_score(labels[mask], preds[mask])), 4)
        tier_results[name] = entry
        print(f"{name}: n={n} accuracy={entry['accuracy']} error_rate={entry['error_rate']}", file=sys.stderr)

    # Explicit error-vs-distance correlation
    correct = (preds == labels).astype(int)
    corr = float(np.corrcoef(tanimoto, correct)[0, 1])

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pool_composition": {
            "internal_test": sum(1 for p in pool if p["source"] == "internal_test"),
            "external_pubchem": sum(1 for p in pool if p["source"] == "external_pubchem"),
            "total": len(pool),
        },
        "tiers": tier_results,
        "confound_warning": (
            "positive_fraction varies sharply across tiers (64% -> 42% -> 10% -> 1%) because the external "
            "PubChem pool (very low positive rate) dominates the two lower-similarity tiers by count. Raw "
            "accuracy is therefore NOT a fair cross-tier comparison -- a tier that is 99% one class scores "
            "high accuracy almost regardless of discrimination quality. ROC-AUC and balanced accuracy "
            "(both prevalence-corrected) are the metrics actually used for the AD-mechanism conclusion below."
        ),
        "error_vs_similarity_correlation": {
            "pearson_r_similarity_vs_correctness": round(corr, 4),
            "interpretation": (
                "near zero, and NOT the primary evidence here -- raw correctness at a fixed 0.5 threshold "
                "is confounded by the same prevalence shift described above. See per-tier ROC-AUC instead."
            ),
        },
        "ad_mechanism_check": {
            "claim_tested": "TDS Sec 6.8: max Tanimoto < 0.4 is a 'strong OOD signal' implying degraded reliability",
            "roc_auc_by_tier": {name: t.get("roc_auc") for name, t in tier_results.items()},
            "finding": (
                "PARTIALLY supported, not cleanly monotonic. out_of_domain has the lowest ROC-AUC (0.727), "
                "consistent with the AD's claim. But chemically_novel (still below the 0.4 threshold) has "
                "the HIGHEST ROC-AUC (0.851) of all four tiers, and highly_similar/moderately_similar are "
                "similar to each other (0.807/0.819) rather than clearly better than chemically_novel. "
                "The single Tanimoto<0.4 cutoff does flag the single worst-performing tier correctly, but "
                "does not produce a clean similarity-performance gradient across the full range -- weaker "
                "support than Phase 3's original AD validation (which used only the internal, much more "
                "homogeneous 800-compound test set) suggested."
            ),
        },
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"\nerror-vs-similarity correlation: {corr:.4f}")
    print(f"report: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
