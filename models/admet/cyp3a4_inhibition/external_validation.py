#!/usr/bin/env python3
"""Phase 9 Sec 12 external validation for the CYP3A4 model.

Source: TDC's "CYP3A4_Veith" dataset (Veith et al. 2009, Nat Biotechnol --
the PubChem AID 1851 qHTS primary screen), fetched directly from its
Harvard Dataverse file (PyTDC's own Python wrapper failed in this
environment -- returned an HTML error page instead of data, the same
"TDC's own download endpoint is blocked" limitation Phase 3's
evaluate.py already documented; the underlying Dataverse file endpoint
itself is reachable directly via plain HTTP, so it was fetched that way
instead of worked around by inventing a substitute).

This is a genuinely INDEPENDENT dataset, not a different split of the same
data: a large-scale PubChem quantitative high-throughput screen (qHTS),
completely separate from the literature-curated ChEMBL IC50 records used
for training. It did not influence training, feature selection,
hyperparameter tuning, or threshold selection at any point -- it was
fetched and processed for the first time here, after the model, its
hyperparameters, and its 10 uM threshold were already fixed.

IMPORTANT CAVEAT, stated plainly rather than glossed over: TDC's Y label
for this dataset comes from PubChem AID 1851's OWN qHTS active/inactive
call, which is a DIFFERENT operationalisation of "CYP3A4 inhibition" than
this model's "aggregated literature IC50 <= 10 uM" definition -- a qHTS
primary screen is typically read at a single high concentration, not a
full dose-response IC50 curve, and PubChem's own active/inactive
threshold logic is not the same procedure as this project's ChEMBL-based
aggregation. Cross-dataset agreement is therefore a genuine but IMPERFECT
proxy for "does this model generalise" -- some disagreement is expected
from label-definition differences alone, not only from model error. This
is reported as a real limitation of this validation step, not hidden.

Usage:
    python models/admet/cyp3a4_inhibition/external_validation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    matthews_corrcoef,
    roc_auc_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from drugsim_chem import DESCRIPTOR_SPEC_VERSION, compute_descriptors, compute_morgan_fingerprint  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402
from drugsim_chem import process_structure  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
EXTERNAL_TSV = ROOT / "datasets" / "raw" / "tdc_cyp3a4_veith_raw.tsv"
TRAINING_DATASET_CSV = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_dataset.csv"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifact"
MODEL_PATH = ARTIFACT_DIR / "model.joblib"
OUTPUT_JSON = Path(__file__).resolve().parent / "external_validation_report.json"

DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


def main() -> int:
    training_df = pd.read_csv(TRAINING_DATASET_CSV)
    training_inchikeys = set(training_df["inchikey_full"])

    external_df = pd.read_csv(EXTERNAL_TSV, sep="\t")
    print(f"loaded {len(external_df)} compounds from TDC CYP3A4_Veith", file=sys.stderr)

    model = joblib.load(MODEL_PATH)

    records = []
    quarantined = 0
    for _, row in external_df.iterrows():
        smiles = row["Drug"]
        try:
            processed = process_structure(smiles)
        except StructureError:
            quarantined += 1
            continue
        if processed.is_mixture:
            continue
        ik = processed.identity.inchikey_full
        records.append({"inchikey_full": ik, "standardized_smiles": processed.standardized_smiles, "label": int(row["Y"])})
        if len(records) % 2000 == 0:
            print(f"  standardised {len(records)}", file=sys.stderr)

    ext_df = pd.DataFrame(records).drop_duplicates(subset="inchikey_full")
    print(f"standardised to {len(ext_df)} unique entities ({quarantined} quarantined)", file=sys.stderr)

    overlap = ext_df["inchikey_full"].isin(training_inchikeys)
    n_overlap = int(overlap.sum())
    disjoint_df = ext_df[~overlap].reset_index(drop=True)
    print(f"overlap with training set: {n_overlap} ({n_overlap / len(ext_df):.1%}); disjoint (genuinely external): {len(disjoint_df)}", file=sys.stderr)

    # Featurise the disjoint set with the exact same pipeline as training.
    descriptor_rows = []
    fingerprints = np.zeros((len(disjoint_df), 2048), dtype=np.uint8)
    for i, row in enumerate(disjoint_df.itertuples()):
        mol = parse_molecule(row.standardized_smiles)
        d = compute_descriptors(mol)
        descriptor_rows.append([getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS])
        fingerprints[i] = compute_morgan_fingerprint(mol)
    descriptors = np.array(descriptor_rows, dtype=np.float64)
    x_ext = np.concatenate([descriptors, fingerprints], axis=1)
    y_ext = disjoint_df["label"].to_numpy()

    y_prob = model.predict_proba(x_ext)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_ext, y_pred).ravel()

    result = {
        "external_dataset": {
            "name": "TDC CYP3A4_Veith (PubChem AID 1851 qHTS primary screen, Veith et al. 2009 Nat Biotechnol)",
            "retrieval_method": "direct HTTP fetch of the underlying Harvard Dataverse file (PyTDC's Python wrapper failed in this environment)",
            "sha256_of_raw_file": __import__("hashlib").sha256(EXTERNAL_TSV.read_bytes()).hexdigest(),
            "n_compounds_raw": int(len(external_df)),
            "n_compounds_standardised": int(len(ext_df)),
            "n_quarantined_unparseable": quarantined,
        },
        "overlap_with_training_data": {
            "n_overlapping_with_chembl_training_set": n_overlap,
            "overlap_fraction": round(n_overlap / len(ext_df), 4),
            "n_genuinely_disjoint": int(len(disjoint_df)),
            "note": "Metrics below are computed ONLY on the disjoint (genuinely unseen) subset.",
        },
        "label_definition_caveat": (
            "TDC's Y label is PubChem AID 1851's own qHTS active/inactive call, a DIFFERENT "
            "operationalisation of 'CYP3A4 inhibition' than this model's 'aggregated ChEMBL "
            "literature IC50 <= 10 uM' definition. Some disagreement is expected from label-"
            "definition differences alone (single-concentration qHTS screening vs. aggregated "
            "dose-response IC50), not only from model error -- this is a real limitation of this "
            "validation, reported here rather than presented as a clean apples-to-apples comparison."
        ),
        "did_not_influence": [
            "training data selection",
            "feature selection",
            "hyperparameter tuning (train.py's validation-group grid search used only ChEMBL group 8)",
            "the 10 uM threshold (fixed before this dataset was ever fetched)",
            "calibration (reliability.py's conformal calibration used only ChEMBL group 7)",
        ],
        "metrics_on_disjoint_external_set": {
            "n": int(len(disjoint_df)),
            "positive_fraction": round(float(y_ext.mean()), 4),
            "roc_auc": round(float(roc_auc_score(y_ext, y_prob)), 4),
            "average_precision_pr_auc": round(float(average_precision_score(y_ext, y_prob)), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_ext, y_pred)), 4),
            "matthews_corrcoef": round(float(matthews_corrcoef(y_ext, y_pred)), 4),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        },
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print(f"\nreport: {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
