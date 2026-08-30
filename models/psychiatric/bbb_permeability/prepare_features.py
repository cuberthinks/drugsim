#!/usr/bin/env python3
"""Compute features and the global scaffold split for the BBB dataset.

Mirrors ``models/psychiatric/cyp2d6_activity/prepare_features.py``
exactly -- same descriptor set, same Morgan fingerprint parameters,
same scaffold-level split-group assignment scheme (ADR-009).
SPLIT_SALT is endpoint-specific ("bbb_permeability_v1").

Usage:
    python models/psychiatric/bbb_permeability/prepare_features.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from drugsim_chem import (  # noqa: E402
    DESCRIPTOR_SPEC_VERSION,
    STANDARDIZATION_PIPELINE_VERSION,
    compute_descriptors,
    compute_morgan_fingerprint,
)
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.version import get_rdkit_version  # noqa: E402
from drugsim_features import compute_feature_set_id  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
DATASET_CSV = ROOT / "datasets" / "processed" / "bbb_permeability_dataset.csv"
OUTPUT_NPZ = ROOT / "datasets" / "processed" / "bbb_permeability_features.npz"
OUTPUT_MANIFEST = ROOT / "datasets" / "processed" / "bbb_permeability_features_manifest.json"

SPLIT_SALT = "bbb_permeability_v1"
N_SPLIT_GROUPS = 10

DESCRIPTOR_FIELDS = [
    "mw_g_mol",
    "exact_mass_g_mol",
    "logp_crippen",
    "molar_refractivity",
    "tpsa_a2",
    "rotatable_bonds",
    "aromatic_rings",
    "ring_count",
    "heavy_atom_count",
    "formal_charge",
    "hbd_lipinski",
    "hba_lipinski",
    "hbd_strict",
    "hba_strict",
    "heteroatom_count",
    "fraction_csp3",
    "num_stereocentres",
    "largest_ring_size",
]


def _split_group(scaffold_key: str) -> int:
    digest = hashlib.sha256(f"{scaffold_key}||{SPLIT_SALT}".encode("utf-8")).hexdigest()
    return int(digest, 16) % N_SPLIT_GROUPS


def main() -> int:
    """Compute features + split assignment and write the feature archive."""
    df = pd.read_csv(DATASET_CSV)
    print(f"loaded {len(df)} compounds", file=sys.stderr)

    descriptor_rows = []
    fingerprints = np.zeros((len(df), 2048), dtype=np.uint8)
    scaffold_keys = []
    for i, row in enumerate(df.itertuples()):
        mol = parse_molecule(row.standardized_smiles)
        d = compute_descriptors(mol)
        descriptor_rows.append([getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS])
        fingerprints[i] = compute_morgan_fingerprint(mol)
        scaffold = row.bemis_murcko_scaffold
        scaffold_keys.append(scaffold if isinstance(scaffold, str) and scaffold else row.standardized_smiles)
        if (i + 1) % 500 == 0:
            print(f"  featurised {i + 1}/{len(df)}", file=sys.stderr)

    descriptors = np.array(descriptor_rows, dtype=np.float64)
    split_groups = np.array([_split_group(k) for k in scaffold_keys], dtype=np.int8)
    labels = df["label"].to_numpy(dtype=np.int8)

    key_to_groups: dict[str, set[int]] = {}
    for key, group in zip(scaffold_keys, split_groups):
        key_to_groups.setdefault(key, set()).add(int(group))
    violating = {k: g for k, g in key_to_groups.items() if len(g) > 1}
    if violating:
        msg = f"{len(violating)} scaffold key(s) mapped to more than one split_group -- must not happen"
        raise AssertionError(msg)

    OUTPUT_NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        OUTPUT_NPZ,
        descriptors=descriptors,
        fingerprints=fingerprints,
        labels=labels,
        split_groups=split_groups,
        local_compound_id=df["local_compound_id"].to_numpy(dtype=object),
        inchikey_full=df["inchikey_full"].to_numpy(dtype=object),
        descriptor_fields=np.array(DESCRIPTOR_FIELDS, dtype=object),
    )

    feature_set_id = compute_feature_set_id(
        descriptor_spec_version=DESCRIPTOR_SPEC_VERSION,
        rdkit_version=str(get_rdkit_version()),
        standardization_pipeline_version=STANDARDIZATION_PIPELINE_VERSION,
        descriptor_names=[*DESCRIPTOR_FIELDS, "morgan_fp_r2_2048"],
    )

    group_counts = {int(g): int((split_groups == g).sum()) for g in range(N_SPLIT_GROUPS)}
    n_acyclic_fallback = sum(1 for k, s in zip(scaffold_keys, df["bemis_murcko_scaffold"]) if not (isinstance(s, str) and s))

    manifest = {
        "feature_set_id": feature_set_id,
        "descriptor_spec_version": DESCRIPTOR_SPEC_VERSION,
        "standardization_pipeline_version": STANDARDIZATION_PIPELINE_VERSION,
        "rdkit_version": get_rdkit_version(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "descriptor_fields": DESCRIPTOR_FIELDS,
        "fingerprint": {"type": "morgan", "radius": 2, "n_bits": 2048},
        "split_assignment": {
            "method": "sha256(scaffold_key || split_salt) mod 10, per ADR-009",
            "split_salt": SPLIT_SALT,
            "acyclic_fallback": "own standardized_smiles used as scaffold_key (singleton group)",
            "n_acyclic_fallback_compounds": n_acyclic_fallback,
            "group_role": {"0-6": "train", "7": "calibration", "8": "validation", "9": "test"},
            "group_counts": group_counts,
        },
        "n_compounds": len(df),
        "output_file": str(OUTPUT_NPZ.relative_to(ROOT)),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote features for {len(df)} compounds to {OUTPUT_NPZ}")
    print(f"split group counts: {group_counts}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
