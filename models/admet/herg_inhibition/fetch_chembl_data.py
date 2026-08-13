#!/usr/bin/env python3
"""Fetch the complete real hERG (CHEMBL240) IC50 activity set from ChEMBL.

Standalone and reproducible: hits ChEMBL's public REST API directly (no
session-specific tooling), paginating through the *entire* result set rather
than a sampled subset. Writes an immutable raw CSV plus a manifest recording
the exact query, retrieval date, and a checksum of the output — the raw file
is never edited in place; re-running this script overwrites it wholesale and
the manifest's checksum is what downstream code should pin against.

Endpoint choice (Phase 3 §1): hERG (CHEMBL240, "Voltage-gated inwardly
rectifying potassium channel KCNH2") is a single, unambiguous, confidence-9
protein target with the deepest and best-characterised bioactivity record of
the ADMET/Tox candidates checked (19,807 combined IC50 records across all
potency bands vs. 13,887 for CYP3A4 and 2,654 for P-glycoprotein) and is the
most externally-benchmarked cardiotoxicity endpoint in cheminformatics.

Usage:
    python models/admet/herg_inhibition/fetch_chembl_data.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_CSV = ROOT / "datasets" / "raw" / "chembl_herg_ic50_raw.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "raw" / "chembl_herg_ic50_manifest.json"

BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
TARGET_CHEMBL_ID = "CHEMBL240"
STANDARD_TYPE = "IC50"
STANDARD_UNITS = "nM"
PAGE_SIZE = 1000

FIELDS = [
    "activity_id",
    "molecule_chembl_id",
    "molecule_pref_name",
    "canonical_smiles",
    "standard_value",
    "standard_units",
    "standard_relation",
    "pchembl_value",
    "assay_type",
    "assay_chembl_id",
    "data_validity_comment",
    "document_chembl_id",
    "document_year",
]


class _TransientAPIError(Exception):
    """Raised for a retryable ChEMBL API failure (timeout, 5xx)."""


def _fetch_page(client: httpx.Client, offset: int) -> dict[str, Any]:
    def _attempt() -> dict[str, Any]:
        try:
            response = client.get(
                BASE_URL,
                params={
                    "target_chembl_id": TARGET_CHEMBL_ID,
                    "standard_type": STANDARD_TYPE,
                    "standard_units": STANDARD_UNITS,
                    "limit": PAGE_SIZE,
                    "offset": offset,
                },
                timeout=30.0,
            )
        except httpx.TransportError as exc:
            raise _TransientAPIError(str(exc)) from exc
        if response.status_code >= 500:
            raise _TransientAPIError(f"HTTP {response.status_code}")
        response.raise_for_status()
        return response.json()

    retrying = Retrying(
        retry=retry_if_exception_type(_TransientAPIError),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    return retrying(_attempt)


def fetch_all_activities() -> list[dict[str, Any]]:
    """Paginate through every matching activity record. Real network I/O."""
    activities: list[dict[str, Any]] = []
    offset = 0
    with httpx.Client() as client:
        while True:
            page = _fetch_page(client, offset)
            batch = page["activities"]
            activities.extend(batch)
            total = page["page_meta"]["total_count"]
            print(f"  fetched {len(activities)}/{total}", file=sys.stderr)
            if page["page_meta"]["next"] is None or not batch:
                break
            offset += PAGE_SIZE
    return activities


def main() -> int:
    """Fetch, filter, write the raw CSV and manifest."""
    print(f"Fetching {TARGET_CHEMBL_ID} {STANDARD_TYPE} activities from ChEMBL...", file=sys.stderr)
    activities = fetch_all_activities()

    rows = []
    dropped_missing = 0
    for a in activities:
        if not a.get("molecule_chembl_id") or not a.get("canonical_smiles"):
            dropped_missing += 1
            continue
        rows.append({field: a.get(field) for field in FIELDS})

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    checksum = hashlib.sha256(OUTPUT_CSV.read_bytes()).hexdigest()
    distinct_compounds = len({r["molecule_chembl_id"] for r in rows})

    manifest = {
        "source": "ChEMBL REST API (direct, standalone)",
        "url": BASE_URL,
        "target_chembl_id": TARGET_CHEMBL_ID,
        "target_name": "Voltage-gated inwardly rectifying potassium channel KCNH2 (hERG / Kv11.1)",
        "standard_type": STANDARD_TYPE,
        "standard_units_filter": STANDARD_UNITS,
        "retrieval_date": datetime.now(timezone.utc).date().isoformat(),
        "total_records_from_api": len(activities),
        "records_dropped_missing_id_or_smiles": dropped_missing,
        "total_records_written": len(rows),
        "distinct_compounds": distinct_compounds,
        "output_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "output_sha256": checksum,
        "note": (
            "Complete population, not a sample -- every IC50/nM activity record "
            "ChEMBL had for this target on the retrieval date, via full "
            "offset/limit pagination. Deduplication and discordance-aware "
            "aggregation across multiple assay records per compound happens "
            "downstream in build_dataset.py, not here. Re-running this script "
            "overwrites both files; the manifest's output_sha256 is what "
            "build_dataset.py should be run against for a given report."
        ),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} rows ({distinct_compounds} distinct compounds) to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
