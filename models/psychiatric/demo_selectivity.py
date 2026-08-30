#!/usr/bin/env python3
"""Verify the selectivity calculation end-to-end on two real reference compounds.

Not the curated "Example Molecules" deliverable (that's this feature's
own later step 17) -- this is a correctness check only: does
`compute_selectivity` produce the right SIGN and a sane magnitude when
fed two real, independently-trained models and two compounds with
well-documented, opposite real-world receptor profiles?

- Haloperidol (CHEMBL54): a classic, potent, first-generation typical
  antipsychotic -- its defining pharmacology is strong D2 antagonism.
- Diphenhydramine (CHEMBL657): a classic first-generation antihistamine
  -- its defining pharmacology is strong H1 antagonism, not an
  antipsychotic at all.

Both SMILES verified against live ChEMBL compound_search during this
work, not typed from memory.

Usage:
    python models/psychiatric/demo_selectivity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402

from selectivity import compute_selectivity  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]

COMPOUNDS = {
    "Haloperidol (CHEMBL54) -- classic potent D2 antagonist": "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1",
    "Diphenhydramine (CHEMBL657) -- classic potent H1 antagonist, not an antipsychotic": "CN(C)CCOC(c1ccccc1)c1ccccc1",
}


def _featurize(smiles: str) -> np.ndarray:
    mol = parse_molecule(smiles)
    d = compute_descriptors(mol)
    descriptors = np.array([[getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]], dtype=np.float64)
    fingerprint = compute_morgan_fingerprint(mol).reshape(1, -1)
    return np.concatenate([descriptors, fingerprint], axis=1), fingerprint


def _load_target(name: str) -> dict:
    base = Path(__file__).resolve().parent / f"{name}_activity"
    model = joblib.load(base / "artifact" / "model.joblib")
    evaluation = json.loads((base / "evaluation_report.json").read_text(encoding="utf-8"))
    features_npz = np.load(ROOT / "datasets" / "processed" / f"{name}_activity_features.npz", allow_pickle=True)
    train_mask = np.isin(features_npz["split_groups"], list(range(7)))
    train_fp = features_npz["fingerprints"][train_mask]
    return {
        "model": model,
        "interval_half_width": evaluation["conformal"]["interval_half_width_pki_units"],
        "tanimoto_threshold": evaluation["applicability_domain"]["thresholds"]["tanimoto_min_for_in_domain"],
        "train_fp": train_fp,
    }


def _tanimoto_max(query_fp: np.ndarray, train_fp: np.ndarray) -> float:
    query_fp = query_fp.astype(np.float32)
    train_fp = train_fp.astype(np.float32)
    intersection = (query_fp @ train_fp.T)[0]
    union = query_fp.sum() + train_fp.sum(axis=1) - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        tanimoto = np.where(union > 0, intersection / union, 0.0)
    return float(tanimoto.max())


def main() -> int:
    """Predict both targets for each reference compound and print the selectivity result."""
    drd2 = _load_target("drd2")
    hrh1 = _load_target("hrh1")

    for label, smiles in COMPOUNDS.items():
        x, fp = _featurize(smiles)

        pki_drd2 = float(drd2["model"].predict(x)[0])
        pki_hrh1 = float(hrh1["model"].predict(x)[0])

        drd2_in_domain = _tanimoto_max(fp, drd2["train_fp"]) >= drd2["tanimoto_threshold"]
        hrh1_in_domain = _tanimoto_max(fp, hrh1["train_fp"]) >= hrh1["tanimoto_threshold"]

        result = compute_selectivity(
            pki_drd2,
            pki_hrh1,
            drd2_uncertainty_half_width=drd2["interval_half_width"],
            hrh1_uncertainty_half_width=hrh1["interval_half_width"],
            drd2_in_domain=drd2_in_domain,
            hrh1_in_domain=hrh1_in_domain,
        )

        print(f"\n=== {label} ===")
        print(f"  predicted DRD2 pKi: {pki_drd2:.2f}   predicted HRH1 pKi: {pki_hrh1:.2f}")
        print(f"  selectivity_index_log10: {result.selectivity_index_log10:+.2f} (uncertainty +/- {result.uncertainty_half_width_log10:.2f})")
        print(f"  fold_selectivity_for_drd2: {result.fold_selectivity_for_drd2:.2f}x")
        print(f"  domain_status: {result.domain_status}")
        print(f"  {result.interpretation}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
