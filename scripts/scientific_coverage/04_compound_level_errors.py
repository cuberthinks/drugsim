"""Scientific Coverage 4: compound-level false positive / false negative sample.

Answers reviewer feedback #2 / brief Section 9 ("for the most important false
positives and false negatives, record compound, experimental outcome,
prediction, applicability-domain status, chemical distance, dataset/source,
model version, likely explanation").

`01_external_generalisation.py` and `03_cyp3a4_external_generalisation.py`
already established that both endpoints have exactly ONE systematic failure
mode -- a base-rate/threshold-mismatch effect, not per-compound idiosyncrasy
(precision falls because the external population is far less enriched for
actives than the internal test set; ROC-AUC, MCC and specificity are flat or
better externally). Their reports deliberately did not list individual
compounds, reasoning that hand-picking "worst offenders" from one already-
diagnosed systematic mode would manufacture narrative confidence the evidence
does not support.

This script produces the compound-level artifact the brief still asks for,
without re-introducing that problem: it draws a **fixed-seed random sample**
(not a "most interesting" or "worst" selection) of external false positives
and false negatives per endpoint, tags each with its real applicability-domain
tier, chemical distance (max Tanimoto to training), dataset/source, and model
version, and gives every row the SAME explanation, because the analysis above
found only one. A per-row "likely explanation" that varied compound-to-compound
would be fabricated -- there is no evidence for compound-specific causes here.

Reuses the two upstream scripts' cached pools (`.pool_cache.json`,
`.cyp3a4_pool_cache.json`) so no model inference is re-run. Read-only.
No model trained, retrained or modified.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = Path(__file__).resolve().parent

# Reuse the exact tier boundaries and threshold from the hERG analysis, same
# load pattern as 03_cyp3a4_external_generalisation.py, so all three reports
# cannot silently diverge in how a tier or threshold is defined.
import importlib.util

_spec = importlib.util.spec_from_file_location("_sc01", OUT_DIR / "01_external_generalisation.py")
_sc01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sc01)

OUTPUT_JSON = OUT_DIR / "04_compound_level_errors_report.json"
SAMPLE_SEED = 42  # matches the project's committed random_seed convention
SAMPLE_SIZE_PER_BUCKET = 15

TIERS = _sc01.TIERS
DEFAULT_THRESHOLD = _sc01.DEFAULT_THRESHOLD

SHARED_EXPLANATION = (
    "Base-rate / operating-point mismatch, not a per-compound failure. The "
    "0.5 decision threshold was set for a population with a much higher "
    "positive fraction than this external set. Ranking quality (ROC-AUC), "
    "MCC and specificity are flat-to-better on this external population than "
    "on the internal test set -- see 01/03_external_generalisation_report.json "
    "-- so no compound-specific cause is evidenced for this false call, and "
    "none is claimed."
)

ENDPOINTS = [
    {
        "endpoint": "herg_inhibition",
        "model_version": "0.1.0",
        "dataset_source": "PubChem AID 588834 (NCATS qHTS hERG screen)",
        "pool_cache": OUT_DIR / ".pool_cache.json",
        # 01_external_generalisation.py's own pool-row tag for its external
        # rows -- the two scripts do not share a source-tag vocabulary.
        "external_source_tag": "external_pubchem",
    },
    {
        "endpoint": "cyp3a4_inhibition",
        "model_version": "0.1.0",
        "dataset_source": "TDC CYP3A4_Veith (PubChem AID 1851 qHTS)",
        "pool_cache": OUT_DIR / ".cyp3a4_pool_cache.json",
        "external_source_tag": "external_tdc",
    },
]


def _tier_for(max_tanimoto: float) -> str:
    for name, lo, hi in TIERS:
        if lo <= max_tanimoto < hi:
            return name
    return "unknown"


def _sample_bucket(rows: list[dict], rng: random.Random, k: int) -> list[dict]:
    chosen = rows if len(rows) <= k else rng.sample(rows, k)
    # Sort by cid for a stable, diff-friendly report -- the sample set is
    # random, but its on-disk order should not be.
    return sorted(chosen, key=lambda r: r.get("cid", ""))


def _build_endpoint_report(cfg: dict) -> dict:
    if not cfg["pool_cache"].exists():
        return {
            "endpoint": cfg["endpoint"],
            "error": (
                f"{cfg['pool_cache'].name} not found -- run "
                f"{'01_external_generalisation.py' if 'herg' in cfg['endpoint'] else '03_cyp3a4_external_generalisation.py'} "
                "first to build it."
            ),
        }

    pool = json.loads(cfg["pool_cache"].read_text())
    external = [p for p in pool if p["source"] == cfg["external_source_tag"]]

    false_positives, false_negatives = [], []
    for row in external:
        pred = 1 if row["prob"] >= DEFAULT_THRESHOLD else 0
        if pred == 1 and row["label"] == 0:
            false_positives.append(row)
        elif pred == 0 and row["label"] == 1:
            false_negatives.append(row)

    rng = random.Random(SAMPLE_SEED)
    fp_sample = _sample_bucket(false_positives, rng, SAMPLE_SIZE_PER_BUCKET)
    fn_sample = _sample_bucket(false_negatives, rng, SAMPLE_SIZE_PER_BUCKET)

    def _row(r: dict, experimental_outcome: str, predicted_label: str) -> dict:
        return {
            "compound": r.get("cid") or r.get("inchikey") or "unknown",
            "experimental_outcome": experimental_outcome,
            "predicted_label": predicted_label,
            "predicted_probability": round(r["prob"], 4),
            "applicability_domain_tier": _tier_for(r["max_tanimoto"]),
            "chemical_distance_max_tanimoto": round(r["max_tanimoto"], 4),
            "dataset_source": cfg["dataset_source"],
            "model_id": cfg["endpoint"],
            "model_version": cfg["model_version"],
            "likely_explanation": SHARED_EXPLANATION,
        }

    return {
        "endpoint": cfg["endpoint"],
        "sampling_method": (
            f"Fixed-seed random sample (seed={SAMPLE_SEED}), not a curated "
            "'most important' selection -- see module docstring for why."
        ),
        "total_false_positives_in_external_pool": len(false_positives),
        "total_false_negatives_in_external_pool": len(false_negatives),
        "false_positive_sample": [
            _row(r, "non_inhibitor (label=0)", "inhibitor (label=1)") for r in fp_sample
        ],
        "false_negative_sample": [
            _row(r, "inhibitor (label=1)", "non_inhibitor (label=0)") for r in fn_sample
        ],
        "systematic_failure_modes_found": 1,
        "note": (
            "Every sampled row carries the same explanation because the upstream "
            "analysis found exactly one systematic mode. This is not a shortcut: "
            "assigning different explanations per row without new evidence would "
            "be the fabrication the brief explicitly warns against."
        ),
    }


def main() -> int:
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": (
            "Compound-level false positive / false negative sample for hERG and "
            "CYP3A4, drawn from the external pools already built by "
            "01_external_generalisation.py and 03_cyp3a4_external_generalisation.py. "
            "Read-only. No model trained, retrained or modified."
        ),
        "endpoints": [_build_endpoint_report(cfg) for cfg in ENDPOINTS],
    }
    OUTPUT_JSON.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
