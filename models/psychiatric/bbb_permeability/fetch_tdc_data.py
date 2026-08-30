#!/usr/bin/env python3
"""Fetch the real BBB permeability dataset (Martins et al.) from TDC.

Per `docs/psychiatric-pipeline/data-sources.md`'s BBB section: TDC
(`datasets/registry.yaml`, `source_id: tdc`) is the already-registered,
already-licensed source for this endpoint -- not B3DB, which has no
governance trail in this project. TDC's own registry entry documents
`retrieval.method: python_package` (PyTDC), but PyTDC's downloader
issues a request without a browser-like User-Agent, which Harvard
Dataverse's file server now answers with an HTTP 403 (confirmed live
during this build -- PyTDC's own cached download at ./data/bbb_martins.tab
is a 199-byte HTML "403 Forbidden" page, not real data). A plain `curl`
to the identical Dataverse file ID succeeds and returns the real
2,039-row dataset. This script fetches the SAME public Dataverse file
PyTDC would, directly via httpx with an explicit User-Agent, mirroring
this repository's own `fetch_chembl_data.py` pattern (standalone,
reproducible, checksum-manifested) rather than depending on PyTDC's
broken-in-this-environment downloader. Same data, same license terms
(TDC/Dataverse, attribution "Therapeutics Data Commons, Harvard (Zitnik
Lab)", registry-approved) -- only the transport differs.

Dataverse file ID (4259566) confirmed via PyTDC's own
`tdc.metadata.name2id["bbb_martins"]`, not guessed.

Usage:
    python models/psychiatric/bbb_permeability/fetch_tdc_data.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_CSV = ROOT / "datasets" / "raw" / "tdc_bbb_martins_raw.csv"
OUTPUT_MANIFEST = ROOT / "datasets" / "raw" / "tdc_bbb_martins_manifest.json"

DATAVERSE_FILE_ID = "4259566"
DATAVERSE_URL = f"https://dataverse.harvard.edu/api/access/datafile/{DATAVERSE_FILE_ID}"
#: Harvard Dataverse's file server rejects requests with no/default
#: User-Agent (HTTP 403) -- this is the one difference from
#: fetch_chembl_data.py's plain httpx.Client() calls.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DrugSimResearch/1.0)"}


class _TransientAPIError(Exception):
    """Raised for a retryable download failure (timeout, 5xx)."""


def _fetch() -> str:
    def _attempt() -> str:
        try:
            with httpx.Client(headers=_HEADERS, follow_redirects=True) as client:
                response = client.get(DATAVERSE_URL, timeout=60.0)
        except httpx.TransportError as exc:
            raise _TransientAPIError(str(exc)) from exc
        if response.status_code >= 500:
            raise _TransientAPIError(f"HTTP {response.status_code}")
        response.raise_for_status()
        text = response.text
        if text.lstrip().startswith("<!DOCTYPE") or text.lstrip().startswith("<html"):
            msg = f"Dataverse returned HTML, not tab-delimited data (first 200 chars: {text[:200]!r})"
            raise RuntimeError(msg)
        return text

    retrying = Retrying(
        retry=retry_if_exception_type(_TransientAPIError),
        stop=stop_after_attempt(4),
        wait=wait_exponential_jitter(initial=1, max=20),
        reraise=True,
    )
    return retrying(_attempt)


def main() -> int:
    """Fetch, parse, write the raw CSV and manifest."""
    print(f"Fetching BBB_Martins from Dataverse file {DATAVERSE_FILE_ID}...", file=sys.stderr)
    raw_text = _fetch()

    reader = csv.DictReader(io.StringIO(raw_text), delimiter="\t")
    rows = []
    dropped_missing = 0
    for r in reader:
        smiles = (r.get("Drug") or "").strip().strip('"')
        label = (r.get("Y") or "").strip()
        drug_id = (r.get("Drug_ID") or "").strip().strip('"')
        if not smiles or label not in ("0", "1"):
            dropped_missing += 1
            continue
        rows.append({"drug_id": drug_id, "smiles": smiles, "bbb_label": int(label)})

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["drug_id", "smiles", "bbb_label"])
        writer.writeheader()
        writer.writerows(rows)

    checksum = hashlib.sha256(OUTPUT_CSV.read_bytes()).hexdigest()
    n_pos = sum(r["bbb_label"] for r in rows)

    manifest = {
        "source": "TDC (Therapeutics Data Commons) -- Martins et al. BBB permeability dataset",
        "source_id": "tdc",
        "dataset_name": "bbb_martins",
        "url": DATAVERSE_URL,
        "retrieval_method": (
            "Direct httpx GET against the same public Dataverse file ID PyTDC's own "
            "tdc.metadata.name2id mapping resolves to, with an explicit User-Agent header -- "
            "PyTDC's own downloader was confirmed live to fail with HTTP 403 in this "
            "environment (no User-Agent set); this is a transport workaround only, not a "
            "different or unvetted data source."
        ),
        "citation": "Martins, I.F. et al. (2012), J Chem Inf Model -- 'A Bayesian approach to in silico blood-brain barrier penetration modeling'",
        "license_note": (
            "Per datasets/registry.yaml's tdc entry: default CC-BY-4.0 / amber tier, "
            "commercial_ok: partial, attribution 'Therapeutics Data Commons, Harvard (Zitnik Lab)'. "
            "BBB_Martins is not in the registry's FreeSolv-style hard exclusion list."
        ),
        "retrieval_date": datetime.now(timezone.utc).date().isoformat(),
        "total_records_written": len(rows),
        "records_dropped_missing_smiles_or_label": dropped_missing,
        "label_distribution_raw": {"bbb_positive_1": n_pos, "bbb_negative_0": len(rows) - n_pos},
        "output_file": str(OUTPUT_CSV.relative_to(ROOT)),
        "output_sha256": checksum,
        "note": (
            "Complete population as published by TDC -- 2,039 compounds, Martins et al.'s own "
            "binary BBB+/BBB- label (already binary at the source; no aggregation/binarization "
            "step is needed the way ChEMBL's continuous IC50/Ki endpoints require). Standardization "
            "and any structure-level dedup happens downstream in build_dataset.py, not here."
        ),
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {len(rows)} rows ({n_pos} BBB+, {len(rows) - n_pos} BBB-) to {OUTPUT_CSV}")
    print(f"manifest: {OUTPUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
