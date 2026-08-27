#!/usr/bin/env python3
"""Compute features and the global scaffold split for the CURATED hERG dataset.

Phase 12 companion to `prepare_features.py`, reading Phase 11's
`datasets/curated/herg_inhibition_curated_compounds.csv` instead of
`datasets/processed/herg_inhibition_dataset.csv`. Never reads from or
writes to `datasets/processed/` -- the production feature set is untouched.

Only `training_eligible == True` rows are used: this drops discordant
compounds (kept-but-flagged by curation, not silently excluded upstream),
compounds with zero usable measurements, and compounds with an unresolved
licence. By construction, every remaining row has a non-null `label`.

The split logic (`SPLIT_SALT`, `N_SPLIT_GROUPS`, `_split_group`) and the
descriptor/fingerprint computation are copied verbatim from
`prepare_features.py`. This is load-bearing, not incidental: identical
split logic means a compound present in both the curated and processed
populations lands in the *same* split_group in both (same scaffold key ->
same hash -> same group), which is what makes a later cross-evaluation
between the two pipelines meaningful.

Usage:
    python models/admet/herg_inhibition/prepare_features_curated.py
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
CURATED_CSV = ROOT / "datasets" / "curated" / "herg_inhibition_curated_compounds.csv"
OUTPUT_NPZ = ROOT / "datasets" / "curated" / "herg_inhibition_features_curated.npz"
OUTPUT_MANIFEST = ROOT / "datasets" / "curated" / "herg_inhibition_features_curated_manifest.json"
PRODUCTION_MANIFEST = ROOT / "datasets" / "processed" / "herg_inhibition_features_manifest.json"

# Identical to prepare_features.py -- must not drift independently.
SPLIT_SALT = "herg_inhibition_v1"
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


def _check_feature_pipeline_parity() -> None:
    """Fail loudly if this pipeline's chemistry differs from production's.

    Both feature-build scripts must derive scaffold keys and descriptors the
    same way for split_group to line up across the two datasets. If
    production's manifest isn't present yet (e.g. a from-scratch checkout),
    this is skipped rather than treated as an error -- there's nothing to
    diverge from yet.
    """
    if not PRODUCTION_MANIFEST.exists():
        print(f"note: {PRODUCTION_MANIFEST} not found, skipping parity check", file=sys.stderr)
        return
    production = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    mismatches = []
    if production["descriptor_spec_version"] != DESCRIPTOR_SPEC_VERSION:
        mismatches.append(f"descriptor_spec_version: {production['descriptor_spec_version']!r} != {DESCRIPTOR_SPEC_VERSION!r}")
    if production["standardization_pipeline_version"] != STANDARDIZATION_PIPELINE_VERSION:
        mismatches.append(
            f"standardization_pipeline_version: {production['standardization_pipeline_version']!r} != {STANDARDIZATION_PIPELINE_VERSION!r}"
        )
    if production["rdkit_version"] != get_rdkit_version():
        mismatches.append(f"rdkit_version: {production['rdkit_version']!r} != {get_rdkit_version()!r}")
    if mismatches:
        detail = "; ".join(mismatches)
        msg = (
            f"curated feature pipeline diverges from production ({detail}) -- "
            "split_group assignment and feature vectors would not be comparable "
            "across the two datasets. Fix the environment before proceeding."
        )
        raise AssertionError(msg)


def main() -> int:
    """Compute features + split assignment for the curated, eligible subset."""
    _check_feature_pipeline_parity()

    df = pd.read_csv(CURATED_CSV)
    n_total = len(df)
    df = df[df["training_eligible"] == True].reset_index(drop=True)  # noqa: E712
    print(f"loaded {n_total} curated compounds, {len(df)} training_eligible", file=sys.stderr)
    if df["label"].isna().any():
        msg = "training_eligible=True row(s) found with a null label -- should not happen by construction"
        raise AssertionError(msg)

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
        if (i + 1) % 2000 == 0:
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
        local_compound_id=df["compound_id"].to_numpy(dtype=object),
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
    n_excluded = n_total - len(df)

    manifest = {
        "feature_set_id": feature_set_id,
        "descriptor_spec_version": DESCRIPTOR_SPEC_VERSION,
        "standardization_pipeline_version": STANDARDIZATION_PIPELINE_VERSION,
        "rdkit_version": get_rdkit_version(),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {
            "curated_compounds_csv": str(CURATED_CSV.relative_to(ROOT)),
            "n_curated_compounds_total": n_total,
            "n_training_eligible": len(df),
            "n_excluded_not_training_eligible": n_excluded,
        },
        "descriptor_fields": DESCRIPTOR_FIELDS,
        "fingerprint": {"type": "morgan", "radius": 2, "n_bits": 2048},
        "split_assignment": {
            "method": "sha256(scaffold_key || split_salt) mod 10, per ADR-009 -- identical to prepare_features.py",
            "split_salt": SPLIT_SALT,
            "acyclic_fallback": "own standardized_smiles used as scaffold_key (singleton group)",
            "n_acyclic_fallback_compounds": n_acyclic_fallback,
            "group_role": {"0-6": "train", "7": "calibration (reserved)", "8": "validation", "9": "test"},
            "group_counts": group_counts,
        },
        "n_compounds": len(df),
        "output_file": str(OUTPUT_NPZ.relative_to(ROOT)),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote features for {len(df)} training-eligible compounds to {OUTPUT_NPZ}")
    print(f"split group counts: {group_counts}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
