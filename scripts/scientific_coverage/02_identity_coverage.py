"""Scientific Coverage 2: compound-identity reference coverage measurement.

Answers external reviewer feedback #1 ("rare/known compounds are not always
identified") with a measurement rather than an impression, and tests -- before
implementing it -- whether the obvious fix is actually safe.

Current resolution (``drugsim_identity.resolve_identity``) is a single exact
full-InChIKey lookup against a committed 960-compound offline snapshot. The
brief's requested resolution order also wants a canonical-structure tier. The
cheminformatically standard candidate is the **InChIKey skeleton** (first 14
characters), which is already computed and carried on ``MolecularIdentity``
but never used for identity resolution.

The skeleton block encodes molecular connectivity only. It deliberately
ignores stereochemistry, isotopes and protonation state -- which is exactly
why it can match more compounds, and exactly why it is *not* proof of
identity. Enantiomers share a skeleton and can differ enormously in
pharmacology. So this script measures two things before anything is changed:

  1. COVERAGE GAIN -- how many otherwise-unresolved public compounds a
     skeleton tier would actually resolve.
  2. COLLISION RISK -- how often one skeleton maps to more than one distinct
     full InChIKey inside the snapshot itself. A colliding skeleton cannot be
     resolved to a single identity without guessing, and guessing identity is
     forbidden.

Test sets are public reference/ChEMBL compounds only. No customer-submitted
structure is read, counted, or reported here (Section 19).

Read-only. Writes `02_identity_coverage_report.json` beside this file.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from drugsim_chem import process_structure  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

SNAPSHOT = ROOT / "src" / "drugsim_identity" / "data" / "compound_identity_snapshot.json"
GOLDEN_CSV = ROOT / "datasets" / "golden" / "compounds.csv"
HERG_NPZ = ROOT / "datasets" / "processed" / "herg_inhibition_features.npz"
CYP_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
OUTPUT_JSON = Path(__file__).resolve().parent / "02_identity_coverage_report.json"


def _load_snapshot() -> tuple[set[str], dict[str, set[str]]]:
    """Return (full-InChIKey set, skeleton -> {full keys} index)."""
    raw = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    full: set[str] = set()
    skeleton: dict[str, set[str]] = defaultdict(set)
    for entry in raw.get("compounds", []):
        key = entry["inchikey_full"]
        full.add(key)
        skeleton[key[:14]].add(key)
    return full, dict(skeleton)


def _coverage(keys: list[str], full: set[str], skeleton: dict[str, set[str]]) -> dict:
    """Resolution outcome for a list of full InChIKeys."""
    exact = 0
    skeleton_unique = 0   # resolvable by skeleton, unambiguously
    skeleton_ambiguous = 0  # skeleton present but maps to >1 identity -> NOT resolvable
    unresolved = 0
    for k in keys:
        if k in full:
            exact += 1
            continue
        candidates = skeleton.get(k[:14])
        if not candidates:
            unresolved += 1
        elif len(candidates) == 1:
            skeleton_unique += 1
        else:
            skeleton_ambiguous += 1
    n = len(keys)

    def rate(x):
        return round(x / n, 4) if n else None

    return {
        "n": n,
        "exact_inchikey_match": exact,
        "exact_inchikey_match_rate": rate(exact),
        "skeleton_match_unambiguous": skeleton_unique,
        "skeleton_match_unambiguous_rate": rate(skeleton_unique),
        "skeleton_match_ambiguous_unusable": skeleton_ambiguous,
        "unresolved": unresolved,
        "unresolved_rate": rate(unresolved),
        "combined_resolvable_rate": rate(exact + skeleton_unique),
        "coverage_gain_from_skeleton_tier": rate(skeleton_unique),
    }


def main() -> int:
    full, skeleton = _load_snapshot()

    # --- collision safety: does one skeleton ever mean two compounds? ---
    colliding = {s: sorted(v) for s, v in skeleton.items() if len(v) > 1}

    strata: dict[str, dict] = {}

    # Stratum A: curated well-known drugs. NOT an independent test -- these
    # SMILES are part of the snapshot's own build input, so this is an upper
    # bound / sanity check, explicitly not evidence of general coverage.
    golden_keys: list[str] = []
    for row in csv.DictReader(GOLDEN_CSV.open()):
        if row["category"] != "drug":
            continue
        try:
            processed = process_structure(row["smiles"])
        except StructureError:
            continue
        golden_keys.append(processed.identity.inchikey_full)
    strata["A_curated_known_drugs_BUILD_INPUT_upper_bound"] = {
        **_coverage(golden_keys, full, skeleton),
        "independence": (
            "NOT INDEPENDENT -- these compounds are part of the snapshot's own build "
            "input (scripts/build_compound_identity_snapshot.py reads golden's "
            "drug-category rows). Reported as an upper bound and sanity check only."
        ),
    }

    # Strata B/C: independent public ChEMBL compounds, never used to seed the
    # snapshot. These are the real coverage numbers.
    for label, npz_path in (("B_public_chembl_herg", HERG_NPZ), ("C_public_chembl_cyp3a4", CYP_NPZ)):
        if not npz_path.exists():
            strata[label] = {"skipped": f"{npz_path.name} not present"}
            continue
        data = np.load(npz_path, allow_pickle=True)
        keys = [str(k) for k in data["inchikey_full"].tolist()]
        strata[label] = {
            **_coverage(keys, full, skeleton),
            "independence": (
                "INDEPENDENT -- public ChEMBL compounds from this endpoint's dataset; "
                "not part of the identity snapshot's seed list."
            ),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Reference-identity coverage only. Says nothing about ADMET model "
            "performance -- reference data and training data are separate concerns "
            "(brief Section 12). Public compounds only; no customer structures."
        ),
        "snapshot": {
            "path": str(SNAPSHOT.relative_to(ROOT)),
            "n_compounds": len(full),
            "n_distinct_skeletons": len(skeleton),
            "current_resolution": "exact full-InChIKey lookup only",
        },
        "skeleton_tier_collision_risk": {
            "n_colliding_skeletons": len(colliding),
            "colliding_examples": dict(list(colliding.items())[:5]),
            "interpretation": (
                "A skeleton mapping to >1 full InChIKey cannot be resolved to a single "
                "identity without guessing. Any skeleton tier must refuse these, not "
                "pick one. Count is the number of such skeletons in the snapshot."
            ),
        },
        "coverage_by_stratum": strata,
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT_JSON.relative_to(ROOT)}")
    print(json.dumps({k: v for k, v in report["coverage_by_stratum"].items()}, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
