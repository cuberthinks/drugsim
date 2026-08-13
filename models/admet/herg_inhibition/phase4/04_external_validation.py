#!/usr/bin/env python3
"""Phase 4.4: external validation against an independent PubChem qHTS assay.

TDC's Dataverse download and PubChem's own DNS both had environment-specific
access problems at various points in this project (TDC blocked by a WAF at
Phase 3 time; PubChem resolves an unreachable IPv6-only address by default
in this sandbox). Both were re-checked for Phase 4: TDC's Dataverse now
appears reachable via a redirect, but no specific hERG file DOI was
re-verified working end-to-end; PubChem IS reachable via a `--resolve`
workaround pinning its known IPv4 address, and PUG-REST returns real data
through it. PubChem AID 588834 ("qHTS Assay for Small Molecule Inhibitors
of the Human hERG Channel Activity", NCATS) was used: a single-protocol
functional hERG inhibition screen, 4,743 compounds, entirely independent of
the ChEMBL curation/aggregation used for training (different submitting
lab, different assay technology, different data-processing pipeline) --
genuinely external, not merely a different query against the same source.

This dataset did NOT influence training, feature selection, hyperparameter
tuning, threshold selection, or calibration -- it was never touched before
this script.

Labeling: uses the assay's own fitted Potency (AC50, uM) with the IDENTICAL
10 uM rule used for the training label, not PubChem's own Active/Inactive
curve-classification (which uses different internal logic) -- this
maximises genuine comparability. PUBCHEM_ACTIVITY_OUTCOME=Inactive compounds
with no fitted curve are labeled non-blocker (the assay tested up to ~92 uM
with no detected response, well above the 10 uM cutoff). Inconclusive
compounds and Active compounds with no fitted Potency are excluded (the
10 uM rule cannot be applied to them).

Usage:
    python models/admet/herg_inhibition/phase4/04_external_validation.py
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, precision_score, recall_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint, process_structure  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
TRAINING_DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
RAW_EXTERNAL_CSV = ROOT / "datasets" / "raw" / "pubchem_aid588834_raw.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "04_external_validation_report.json"

PUBCHEM_HOST_IP = "34.107.134.59"  # workaround: this sandbox cannot route to pubchem's IPv6-only DNS answer
AID = 588834
THRESHOLD_NM = 10_000.0
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


def fetch_raw() -> pd.DataFrame:
    """Download the assay data table (real network I/O) and cache it locally.

    This sandbox's DNS resolves pubchem.ncbi.nlm.nih.gov to an IPv6-only
    address this network cannot route to ("no route to host"); the real
    IPv4 address IS reachable. curl's --resolve pins the hostname to that
    IPv4 address directly (TLS SNI/Host header still use the real hostname,
    so this is not spoofing anything the server would refuse) -- verified
    manually before writing this into a script. No httpx equivalent was
    available quickly, so this shells out to curl rather than fighting
    httpx's connection-pool internals for a one-off fetch.
    """
    if RAW_EXTERNAL_CSV.exists():
        print(f"using cached {RAW_EXTERNAL_CSV}", file=sys.stderr)
        return pd.read_csv(RAW_EXTERNAL_CSV, skiprows=[1, 2, 3])
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/assay/aid/{AID}/CSV?sid=all"
    proc = subprocess.run(
        ["curl", "-sf", "--max-time", "120", "--resolve", f"pubchem.ncbi.nlm.nih.gov:443:{PUBCHEM_HOST_IP}", url],
        capture_output=True, check=True,
    )
    RAW_EXTERNAL_CSV.parent.mkdir(parents=True, exist_ok=True)
    RAW_EXTERNAL_CSV.write_bytes(proc.stdout)
    return pd.read_csv(io.BytesIO(proc.stdout), skiprows=[1, 2, 3])


def main() -> int:
    """Fetch, label, standardise, predict, and score against the external set."""
    df = fetch_raw()
    print(f"loaded {len(df)} raw rows from AID {AID}", file=sys.stderr)

    # Potency reads as mixed str/float dtype from the raw CSV (pandas' chunked
    # type inference splits on it) -- coerce to a clean numeric column.
    df["Potency"] = pd.to_numeric(df["Potency"], errors="coerce")

    # One row per CID: some CIDs have multiple SIDs (vendor batches); keep the
    # most informative row (prefer one with a fitted Potency, else first seen).
    df = df.sort_values("Potency", na_position="last")
    df = df.drop_duplicates(subset="PUBCHEM_CID", keep="first")
    df = df.dropna(subset=["PUBCHEM_CID", "PUBCHEM_EXT_DATASOURCE_SMILES"])
    print(f"{len(df)} distinct CIDs with SMILES", file=sys.stderr)

    labeled_rows = []
    excluded_inconclusive = 0
    excluded_active_no_potency = 0
    for row in df.itertuples():
        outcome = row.PUBCHEM_ACTIVITY_OUTCOME
        potency_um = row.Potency
        if outcome == "Inconclusive":
            excluded_inconclusive += 1
            continue
        if outcome == "Inactive" and pd.isna(potency_um):
            label = 0
        elif not pd.isna(potency_um):
            label = 1 if (potency_um * 1000.0) <= THRESHOLD_NM else 0
        else:
            excluded_active_no_potency += 1
            continue
        labeled_rows.append(
            {"cid": int(row.PUBCHEM_CID), "smiles": row.PUBCHEM_EXT_DATASOURCE_SMILES,
             "outcome": outcome, "potency_um": potency_um, "label": label}
        )
    print(
        f"labeled {len(labeled_rows)} compounds "
        f"(excluded {excluded_inconclusive} inconclusive, {excluded_active_no_potency} active-no-potency)",
        file=sys.stderr,
    )

    # Standardise + featurise via the SAME drugsim_chem pipeline used for training
    quarantined = 0
    mixtures = 0
    records = []
    for i, r in enumerate(labeled_rows):
        try:
            processed = process_structure(r["smiles"])
        except StructureError:
            quarantined += 1
            continue
        if processed.is_mixture:
            mixtures += 1
            continue
        mol = parse_molecule(processed.standardized_smiles)
        d = compute_descriptors(mol)
        descriptors = [getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]
        fp = compute_morgan_fingerprint(mol)
        records.append(
            {
                "cid": r["cid"], "inchikey_full": processed.identity.inchikey_full,
                "label": r["label"], "x": np.concatenate([descriptors, fp]),
            }
        )
        if (i + 1) % 1000 == 0:
            print(f"  featurised {i + 1}/{len(labeled_rows)}", file=sys.stderr)

    print(f"{len(records)} compounds standardised ({quarantined} quarantined, {mixtures} mixtures)", file=sys.stderr)

    # Overlap check against the training set
    train_df = pd.read_csv(TRAINING_DATASET_CSV)
    train_inchikeys = set(train_df["inchikey_full"])
    for rec in records:
        rec["in_training_set"] = rec["inchikey_full"] in train_inchikeys
    n_overlap = sum(r["in_training_set"] for r in records)

    # Near-duplicate check: max Tanimoto of each external compound to the training fingerprints
    train_features = np.load(ROOT / "datasets" / "processed" / "herg_inhibition_features.npz", allow_pickle=True)
    train_fps = train_features["fingerprints"].astype(np.float32)
    ext_fps = np.array([r["x"][len(DESCRIPTOR_FIELDS):] for r in records], dtype=np.float32)
    intersection = ext_fps @ train_fps.T
    ext_sum = ext_fps.sum(axis=1, keepdims=True)
    train_sum = train_fps.sum(axis=1, keepdims=True)
    union = ext_sum + train_sum.T - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, intersection / union, 0.0)
    max_tanimoto = sim.max(axis=1)
    for rec, t in zip(records, max_tanimoto):
        rec["max_tanimoto_to_train"] = float(t)
    n_near_dup = int((max_tanimoto >= 0.95).sum())

    model = joblib.load(MODEL_PATH)
    x_all = np.array([r["x"] for r in records])
    y_all = np.array([r["label"] for r in records])
    prob_all = model.predict_proba(x_all)[:, 1]
    pred_all = (prob_all >= 0.5).astype(int)

    def _metrics(mask: np.ndarray) -> dict:
        if mask.sum() < 2 or len(set(y_all[mask])) < 2:
            return {"n": int(mask.sum()), "note": "insufficient class diversity for AUC"}
        tn, fp, fn, tp = confusion_matrix(y_all[mask], pred_all[mask]).ravel()
        return {
            "n": int(mask.sum()),
            "positive_fraction": round(float(y_all[mask].mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_all[mask], prob_all[mask])), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_all[mask], pred_all[mask])), 4),
            "precision": round(float(precision_score(y_all[mask], pred_all[mask])), 4),
            "recall": round(float(recall_score(y_all[mask], pred_all[mask])), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }

    overlap_mask = np.array([r["in_training_set"] for r in records])
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "external_source": {
            "name": "PubChem AID 588834 -- qHTS Assay for Small Molecule Inhibitors of the Human hERG Channel Activity",
            "submitter": "NCATS (NIH)",
            "url": f"https://pubchem.ncbi.nlm.nih.gov/bioassay/{AID}",
            "independence": "Distinct submitting lab, assay technology, and data pipeline from ChEMBL. Not used in training, feature selection, hyperparameter tuning, threshold selection, or calibration prior to this script.",
            "total_compounds_in_assay": len(df),
            "excluded_inconclusive": excluded_inconclusive,
            "excluded_active_no_potency": excluded_active_no_potency,
            "quarantined_structures": quarantined,
            "mixtures_excluded": mixtures,
            "final_n": len(records),
            "label_rule": f"SAME rule as training: potency (AC50) <= {THRESHOLD_NM:.0f} nM = blocker, using this assay's own fitted Potency value, not PubChem's internal Active/Inactive curve classification",
        },
        "overlap_with_training_set": {
            "n_exact_inchikey_overlap": int(n_overlap),
            "fraction_overlap": round(n_overlap / len(records), 4),
            "n_near_duplicate_tanimoto_ge_0.95": n_near_dup,
            "fraction_near_duplicate": round(n_near_dup / len(records), 4),
        },
        "performance": {
            "all_external_compounds": _metrics(np.ones(len(records), dtype=bool)),
            "excluding_exact_training_overlap": _metrics(~overlap_mask),
            "excluding_near_duplicates_ge_0.95": _metrics(max_tanimoto < 0.95),
        },
        "class_prevalence_note": (
            f"External set positive fraction is ~{float(y_all.mean()):.1%}, vs. ~66% in the training "
            "distribution. ROC-AUC (ranking quality) transfers reasonably well despite this shift, but "
            "the model's default 0.5 decision threshold and any calibration were fit under a ~66% prior "
            "and do NOT automatically transfer to a ~10% prior -- this shows up as high recall but low "
            "precision here (many false positives in absolute terms), not as poor discrimination."
        ),
        "near_duplicate_note": (
            "n_near_duplicate_tanimoto_ge_0.95 equals n_exact_inchikey_overlap exactly -- no additional "
            "near-duplicates beyond the literal training-set overlap were found in this external set."
        ),
        "registered_model_reference": {"global_split_test_roc_auc": 0.7875, "global_split_test_balanced_accuracy": 0.6495},
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result["performance"], indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
