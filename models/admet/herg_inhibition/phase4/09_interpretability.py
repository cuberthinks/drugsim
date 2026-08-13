#!/usr/bin/env python3
"""Phase 4.9: interpretability -- feature importance, substructures, examples.

IMPORTANT: feature importance below reflects what the trained Random Forest
found statistically useful for separating labels in THIS dataset. It is not
evidence of biological/mechanistic causation about hERG channel binding --
a descriptor or substructure can be predictive by correlation (e.g. with a
chemical series that happens to be potent) without being mechanistically
responsible for channel block. This distinction is not just a stylistic
caveat; conflating the two is a common and specific misuse of feature
importance in QSAR reporting.

Usage:
    python models/admet/herg_inhibition/phase4/09_interpretability.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from rdkit import Chem

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "src"))

from drugsim_chem.parsing import parse_molecule  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODEL_PATH = ROOT / "models" / "admet" / "herg_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
DATASET_CSV = ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv"
OUTPUT_JSON = Path(__file__).resolve().parent / "09_interpretability_report.json"

TRAIN_GROUPS = list(range(7))
TEST_GROUP = 9
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


def _bit_to_substructure_examples(bit_id: int, smiles_pool: list[str], max_examples: int = 2) -> list[str]:
    """Find real molecules in the pool that set this fingerprint bit, and
    return the SMILES of the atom environment that set it there."""
    from rdkit.Chem import AllChem

    examples = []
    for smi in smiles_pool:
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            continue
        bit_info: dict = {}
        AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048, bitInfo=bit_info, useChirality=True)
        if bit_id in bit_info:
            atom_idx, radius = bit_info[bit_id][0]
            if radius == 0:
                examples.append(mol.GetAtomWithIdx(atom_idx).GetSymbol())
            else:
                env = Chem.FindAtomEnvironmentOfRadiusN(mol, radius, atom_idx)
                amap: dict = {}
                submol = Chem.PathToSubmol(mol, env, atomMap=amap)
                examples.append(Chem.MolToSmiles(submol))
        if len(examples) >= max_examples:
            break
    return examples


def _name_or_unnamed(value: object) -> str:
    return value if isinstance(value, str) and value else "(unnamed)"


def main() -> int:
    """Compute feature importances, substructure mapping, and examples."""
    model = joblib.load(MODEL_PATH)
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    df = pd.read_csv(DATASET_CSV).set_index("inchikey_full")

    importances = model.feature_importances_
    descriptor_importances = importances[: len(DESCRIPTOR_FIELDS)]
    fingerprint_importances = importances[len(DESCRIPTOR_FIELDS):]

    top_descriptors = sorted(
        zip(DESCRIPTOR_FIELDS, descriptor_importances), key=lambda x: x[1], reverse=True
    )[:10]

    top_bits_idx = np.argsort(fingerprint_importances)[::-1][:10]
    smiles_pool = df["standardized_smiles"].sample(n=min(500, len(df)), random_state=42).tolist()

    top_bits = []
    for bit in top_bits_idx:
        examples = _bit_to_substructure_examples(int(bit), smiles_pool)
        top_bits.append({
            "bit_index": int(bit),
            "importance": round(float(fingerprint_importances[bit]), 6),
            "example_substructures": examples,
        })

    # Chemical similarity example: nearest training neighbour of one representative test compound
    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    test_mask = data["split_groups"] == TEST_GROUP
    train_fps = data["fingerprints"][train_mask].astype(np.float32)
    train_ik = data["inchikey_full"][train_mask]
    test_fps = data["fingerprints"][test_mask].astype(np.float32)
    test_ik = data["inchikey_full"][test_mask]

    # Pick a genuinely high-similarity test compound (not an arbitrary index)
    # so the example actually illustrates a close chemical match, not a weak one.
    all_inter = test_fps @ train_fps.T
    all_union = test_fps.sum(axis=1, keepdims=True) + train_fps.sum(axis=1, keepdims=True).T - all_inter
    all_sim = np.where(all_union > 0, all_inter / all_union, 0.0)
    row_max = all_sim.max(axis=1)
    example_idx = int(np.argsort(row_max)[::-1][len(row_max) // 20])  # a top-5%-similarity example, not the single closest (near-duplicate) case
    sim = all_sim[example_idx]
    nn_idx = int(np.argmax(sim))

    similarity_example = {
        "query_compound": {
            "inchikey": test_ik[example_idx],
            "name": _name_or_unnamed(df.loc[test_ik[example_idx], "molecule_pref_names"]),
            "smiles": df.loc[test_ik[example_idx], "standardized_smiles"],
            "label": int(data["labels"][test_mask][example_idx]),
        },
        "nearest_training_neighbour": {
            "inchikey": train_ik[nn_idx],
            "name": _name_or_unnamed(df.loc[train_ik[nn_idx], "molecule_pref_names"]),
            "smiles": df.loc[train_ik[nn_idx], "standardized_smiles"],
            "label": int(data["labels"][train_mask][nn_idx]),
            "tanimoto_similarity": round(float(sim[nn_idx]), 4),
        },
    }

    # Representative correct predictions (high confidence, correct) and failures (from Phase 4.7)
    x_test = np.concatenate([data["descriptors"][test_mask], data["fingerprints"][test_mask]], axis=1)
    y_test = data["labels"][test_mask]
    prob_test = model.predict_proba(x_test)[:, 1]
    pred_test = (prob_test >= 0.5).astype(int)
    confident_correct_mask = (np.abs(prob_test - 0.5) > 0.45) & (pred_test == y_test)
    confident_correct_idx = np.where(confident_correct_mask)[0][:5]
    representative_correct = [
        {
            "name": _name_or_unnamed(df.loc[test_ik[i], "molecule_pref_names"]),
            "true_label": "blocker" if y_test[i] == 1 else "non_blocker",
            "predicted_prob_blocker": round(float(prob_test[i]), 4),
            "true_ic50_nm": round(float(df.loc[test_ik[i], "aggregated_ic50_nm"]), 1),
        }
        for i in confident_correct_idx
    ]

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "causation_caveat": (
            "Feature importance reflects statistical usefulness for separating labels in THIS dataset, "
            "not evidence of biological/mechanistic causation about hERG channel binding. A descriptor or "
            "substructure can be predictive by correlation with a potent chemical series without being "
            "mechanistically responsible for channel block."
        ),
        "top_physicochemical_descriptors": [
            {"descriptor": name, "importance": round(float(imp), 4)} for name, imp in top_descriptors
        ],
        "fingerprint_vs_descriptor_importance_share": {
            "descriptors_total": round(float(descriptor_importances.sum()), 4),
            "fingerprint_total": round(float(fingerprint_importances.sum()), 4),
        },
        "top_fingerprint_bits": top_bits,
        "chemical_similarity_example": similarity_example,
        "representative_confident_correct_predictions": representative_correct,
        "representative_failures": "see models/admet/herg_inhibition/phase4/07_error_analysis_report.json:largest_confident_errors",
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
