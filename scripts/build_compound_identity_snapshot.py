#!/usr/bin/env python3
"""Build the offline compound-identity snapshot from PubChem, once.

This is the ONLY place in the codebase that calls PubChem. It runs
offline, as an operator-triggered batch script -- never as part of the
live `/predict` request path, which only ever reads the resulting
committed JSON file (`src/drugsim_identity/data/compound_identity_
snapshot.json`). This is what keeps DrugSim's existing, tested privacy
guarantee intact: no third-party service ever receives a user-submitted
structure (`docs/privacy/confidentiality-audit.md` Sec 8) -- every
structure this script resolves comes from DrugSim's own already-approved
reference data (`datasets/golden/compounds.csv`'s named drugs, plus
`src/drugsim_identity/data/seed_compounds.yaml`), never from a live user
submission.

Reuses `drugsim_chem.process_structure` for standardisation/InChIKey
(never reimplemented) and `drugsim_curation.provenance.resolve_license`
for the same fail-closed licence check Phase 11 already established --
called once against the "pubchem" registry entry before any network call.

Usage:
    python scripts/build_compound_identity_snapshot.py
    python scripts/build_compound_identity_snapshot.py --no-network  # rebuild snapshot.json from a local cache only
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drugsim_chem import process_structure  # noqa: E402
from drugsim_curation.provenance import SourceRegistry, resolve_license  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEED_YAML = ROOT / "src" / "drugsim_identity" / "data" / "seed_compounds.yaml"
GOLDEN_COMPOUNDS_CSV = ROOT / "datasets" / "golden" / "compounds.csv"
OUTPUT_SNAPSHOT = ROOT / "src" / "drugsim_identity" / "data" / "compound_identity_snapshot.json"
REGISTRY_PATH = ROOT / "datasets" / "registry.yaml"

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_VIEW_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
REQUEST_DELAY_SECONDS = 0.25  # PubChem's documented courtesy limit is <=5 req/s.
MAX_SYNONYMS = 5

# Golden fixtures whose name is a deliberate "shaped like a real drug" test
# structure, not the literal compound -- must never be sent to PubChem as
# if it were real.
GOLDEN_EXCLUDE_NAMES = frozenset({"imatinib_like"})


def _load_seed_smiles() -> list[str]:
    """Every SMILES worth enriching: golden's real-drug fixtures + the seed YAML."""
    smiles_list: list[str] = []

    with GOLDEN_COMPOUNDS_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["category"] == "drug" and row["name"] not in GOLDEN_EXCLUDE_NAMES:
                smiles_list.append(row["smiles"])

    seed = yaml.safe_load(SEED_YAML.read_text(encoding="utf-8"))
    for entry in seed.get("compounds", []):
        smiles_list.append(entry["smiles"])

    return smiles_list


def _fetch_cid(client: httpx.Client, inchikey: str) -> str | None:
    resp = client.get(f"{PUBCHEM_BASE}/compound/inchikey/{inchikey}/cids/JSON")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    cids = resp.json().get("IdentifierList", {}).get("CID", [])
    return str(cids[0]) if cids else None


def _fetch_name(client: httpx.Client, cid: str) -> str | None:
    resp = client.get(f"{PUBCHEM_BASE}/compound/cid/{cid}/property/Title/JSON")
    resp.raise_for_status()
    props = resp.json().get("PropertyTable", {}).get("Properties", [])
    return props[0].get("Title") if props else None


def _fetch_synonyms(client: httpx.Client, cid: str, preferred_name: str) -> list[str]:
    resp = client.get(f"{PUBCHEM_BASE}/compound/cid/{cid}/synonyms/JSON")
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    info = resp.json().get("InformationList", {}).get("Information", [])
    if not info:
        return []
    all_synonyms = info[0].get("Synonym", [])
    out = []
    for syn in all_synonyms:
        if syn.strip().lower() == preferred_name.strip().lower():
            continue
        out.append(syn)
        if len(out) >= MAX_SYNONYMS:
            break
    return out


def _find_description_section(sections: list[dict]) -> dict | None:
    for section in sections:
        if section.get("TOCHeading") == "Record Description":
            return section
        nested = section.get("Section")
        if nested:
            found = _find_description_section(nested)
            if found is not None:
                return found
    return None


def _fetch_description(client: httpx.Client, cid: str) -> tuple[str | None, str | None]:
    """Return (description, source) from PubChem's own PUG-View data, or (None, None)."""
    resp = client.get(f"{PUBCHEM_VIEW_BASE}/data/compound/{cid}/JSON", params={"heading": "Record Description"})
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    sections = resp.json().get("Record", {}).get("Section", [])
    section = _find_description_section(sections)
    if section is None:
        return None, None
    for info in section.get("Information", []):
        value = info.get("Value", {}).get("StringWithMarkup", [])
        if not value:
            continue
        text = value[0].get("String")
        if not text:
            continue
        reference = info.get("Reference")
        source = f"PubChem ({reference[0]})" if reference else "PubChem"
        return text, source
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-network", action="store_true", help="Skip PubChem calls; keep existing snapshot entries only.")
    args = parser.parse_args()

    registry = SourceRegistry.load(REGISTRY_PATH)
    license_resolution = resolve_license(registry, "pubchem")
    if license_resolution.license_status != "resolved":
        msg = f"pubchem licence did not resolve: {license_resolution.reason}"
        raise RuntimeError(msg)
    print(f"pubchem licence resolved: {license_resolution.spdx} (commercial_ok={license_resolution.commercial_ok})", file=sys.stderr)

    existing: dict[str, dict] = {}
    if OUTPUT_SNAPSHOT.exists():
        existing = {c["inchikey_full"]: c for c in json.loads(OUTPUT_SNAPSHOT.read_text(encoding="utf-8"))["compounds"]}

    smiles_list = _load_seed_smiles()
    print(f"resolving {len(smiles_list)} seed compounds", file=sys.stderr)

    compounds: dict[str, dict] = dict(existing)
    skipped: list[str] = []

    if not args.no_network:
        with httpx.Client(timeout=10.0, headers={"User-Agent": "DrugSim/1.0 (compound-identity-snapshot-builder)"}) as client:
            for smiles in smiles_list:
                processed = process_structure(smiles)
                inchikey = processed.identity.inchikey_full
                if inchikey in compounds:
                    continue  # already resolved in a prior run
                try:
                    time.sleep(REQUEST_DELAY_SECONDS)
                    cid = _fetch_cid(client, inchikey)
                    if cid is None:
                        print(f"  no PubChem CID for {smiles!r} ({inchikey}) -- skipping", file=sys.stderr)
                        skipped.append(smiles)
                        continue
                    time.sleep(REQUEST_DELAY_SECONDS)
                    name = _fetch_name(client, cid)
                    if not name:
                        print(f"  PubChem CID {cid} has no Title -- skipping {smiles!r}", file=sys.stderr)
                        skipped.append(smiles)
                        continue
                    time.sleep(REQUEST_DELAY_SECONDS)
                    synonyms = _fetch_synonyms(client, cid, name)
                    time.sleep(REQUEST_DELAY_SECONDS)
                    description, description_source = _fetch_description(client, cid)
                except httpx.HTTPError as exc:
                    # A per-compound network failure is logged and skipped, never
                    # fatal to the whole batch -- one unreachable compound must not
                    # corrupt or discard everything already resolved.
                    print(f"  fetch failed for {smiles!r} ({inchikey}): {exc} -- skipping", file=sys.stderr)
                    skipped.append(smiles)
                    continue

                compounds[inchikey] = {
                    "inchikey_full": inchikey,
                    "pubchem_cid": cid,
                    "preferred_name": name,
                    "synonyms": synonyms,
                    "description": description,
                    "description_source": description_source,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "license_spdx": license_resolution.spdx,
                }
                print(f"  resolved {smiles!r} -> {name!r} (CID {cid})", file=sys.stderr)

    OUTPUT_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_SNAPSHOT.write_text(
        json.dumps({"compounds": list(compounds.values())}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(compounds)} compounds to {OUTPUT_SNAPSHOT}")
    if skipped:
        print(f"skipped {len(skipped)} compound(s) (no PubChem match or fetch failure): {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
