#!/usr/bin/env python3
"""Fetch the complete real DRD2 (CHEMBL217) Ki activity set from ChEMBL.

Mirrors `models/admet/herg_inhibition/fetch_chembl_data.py` exactly (same
standalone, paginate-the-whole-population approach, same raw/manifest
output convention) -- the only differences are the target and the
activity type.

Endpoint choice (`docs/psychiatric-pipeline/data-sources.md`): Ki, not
IC50 -- Ki is a true binding-affinity measurement (assay-independent),
dominant for this target (14,842 Ki vs. 2,480 IC50 records, live-verified
during this feature's data-source audit), and pooling Ki with IC50
without justification is explicitly something this project's own
psychiatric-pipeline brief warns against.

Usage:
    python models/psychiatric/drd2_activity/fetch_chembl_data.py
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
OUTPUT_CSV = ROOT / "datasets" / "raw" / "chembl_drd2_ki_raw.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "raw" / "chembl_drd2_ki_manifest.json"

BASE_URL = "https://www.ebi.ac.uk/chembl/api/data/activity.json"
TARGET_CHEMBL_ID = "CHEMBL217"
STANDARD_TYPE = "Ki"
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
        "target_name": "D(2) dopamine receptor (DRD2)",
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
            "Complete population, not a sample -- every Ki/nM activity record "
            "ChEMBL had for CHEMBL217 on the retrieval date, via full "
            "offset/limit pagination. Deduplication and discordance-aware "
            "aggregation across multiple assay records per compound happens "
            "downstream in build_dataset.py, not here."
        ),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} rows ({distinct_compounds} distinct compounds) to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
