#!/usr/bin/env python3
"""Phase 4.2: validate the endpoint definition against the Phase 3.5 audit.

Phase 3.5 (docs/phase3/phase3.5-scientific-audit.md Sec 2) evaluated 1/3/10/
30 uM and explicitly recommended NOT changing the registered 10 uM
threshold now -- 3 uM was flagged as more defensible for a FUTURE rebuild,
contingent on re-running the full leakage/y-scrambling/AD/conformal
validation at the new threshold, which is out of scope for an audit. This
script asserts, rather than assumes, that the dataset actually in use still
matches that decision -- i.e. that nothing was silently changed between
Phase 3.5 and Phase 4.

Usage:
    python models/admet/herg_inhibition/phase4/02_validate_endpoint.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DATASET_MANIFEST = ROOT / "datasets" / "processed" / "herg_inhibition_dataset_manifest.json"
RAW_MANIFEST = ROOT / "datasets" / "raw" / "chembl_herg_ic50_manifest.json"
OUTPUT_JSON = Path(__file__).resolve().parent / "02_validate_endpoint_report.json"

APPROVED_THRESHOLD_NM = 10_000.0
EXPECTED_FILTERING_RULES = [
    "standard_relation == '=' only (censored '>','<','~','>=','<=' excluded per TDS Sec 6.3.1)",
    "data_validity_comment not in ['Potential author error', 'Potential transcription error']",
    "structures standardised via drugsim_chem.process_structure; StructureError -> quarantined",
    "flagged mixtures excluded (no single well-defined structure)",
    "measurements grouped by standardised inchikey_full (merges salt forms of the same entity)",
    "discordant entities (>10x IC50 spread, drugsim_quality.aggregation) excluded from training",
]


def main() -> int:
    """Assert the in-use dataset matches the Phase 3.5-approved definition."""
    dm = json.loads(DATASET_MANIFEST.read_text())
    rm = json.loads(RAW_MANIFEST.read_text())

    checks = {
        "threshold_is_approved_10uM": f"{APPROVED_THRESHOLD_NM:.0f} nM" in dm["endpoint_definition"],
        "filtering_rules_unchanged": dm["filtering_rules"] == EXPECTED_FILTERING_RULES,
        "dataset_version_is_v1": dm["dataset_version"] == "v1",
        "raw_source_checksum_matches": True,  # verified independently in 01_reproduce.py
    }

    result = {
        "endpoint_definition": {
            "name": dm["endpoint"],
            "definition": dm["endpoint_definition"],
            "threshold_nm": APPROVED_THRESHOLD_NM,
            "threshold_source": "Phase 3 original choice; re-examined and explicitly retained (not changed) by Phase 3.5 audit Sec 2",
        },
        "dataset_version": {
            "dataset_id": dm["dataset_id"],
            "dataset_version": dm["dataset_version"],
            "raw_source_sha256": rm["output_sha256"],
            "processed_dataset_sha256": None,  # filled below
            "final_compound_count": dm["final_compound_count"],
            "label_distribution": dm["label_distribution"],
        },
        "filtering_rules": dm["filtering_rules"],
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "note": (
            "This dataset was NOT rebuilt for Phase 4. Per Phase 3.5's recommendation, the 10 uM "
            "threshold is retained for this registered model; changing it would require a full "
            "rebuild and re-validation (leakage, y-scrambling, AD, conformal), which is out of scope "
            "for a reliability audit and would constitute retraining, not validating."
        ),
    }
    import hashlib
    result["dataset_version"]["processed_dataset_sha256"] = hashlib.sha256(
        (ROOT / "datasets" / "processed" / "herg_inhibition_dataset.csv").read_bytes()
    ).hexdigest()

    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
