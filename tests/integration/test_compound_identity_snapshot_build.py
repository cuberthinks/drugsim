"""One real round-trip against PubChem's live PUG-REST/PUG-View endpoints.

Every other compound-identity test uses the committed snapshot (fast,
deterministic). This file proves the build script's real network calls
still resolve real compounds the way the snapshot's own data claims --
mirroring tests/integration/test_curation_assay_context_live.py's
convention for the same reason.

Target: caffeine and aspirin -- small, extremely well-characterised
PubChem entries whose CID/name have been stable for decades.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from drugsim_chem import process_structure  # noqa: E402

from build_compound_identity_snapshot import (  # noqa: E402
    _fetch_cid,
    _fetch_description,
    _fetch_name,
    _fetch_synonyms,
)

pytestmark = [pytest.mark.integration, pytest.mark.network]

CAFFEINE_SMILES = "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"


def test_caffeine_resolves_via_the_real_pubchem_api() -> None:
    inchikey = process_structure(CAFFEINE_SMILES).identity.inchikey_full
    with httpx.Client(timeout=10.0) as client:
        cid = _fetch_cid(client, inchikey)
        assert cid == "2519"
        name = _fetch_name(client, cid)
        assert name == "Caffeine"
        synonyms = _fetch_synonyms(client, cid, name)
        assert len(synonyms) > 0
        assert "caffeine" not in [s.lower() for s in synonyms]  # the preferred name itself is excluded


def test_aspirin_resolves_via_the_real_pubchem_api() -> None:
    inchikey = process_structure(ASPIRIN_SMILES).identity.inchikey_full
    with httpx.Client(timeout=10.0) as client:
        cid = _fetch_cid(client, inchikey)
        assert cid == "2244"
        name = _fetch_name(client, cid)
        assert name == "Aspirin"


def test_description_fetch_returns_sourced_text_when_available() -> None:
    with httpx.Client(timeout=10.0) as client:
        description, source = _fetch_description(client, "2519")
    assert description is not None
    assert len(description) > 0
    assert source is not None and "PubChem" in source


def test_unresolvable_inchikey_returns_no_cid() -> None:
    """A made-up InChIKey must resolve to None, not raise -- this is the
    real-world case behind 'compound not found', not a network error."""
    with httpx.Client(timeout=10.0) as client:
        cid = _fetch_cid(client, "AAAAAAAAAAAAAA-AAAAAAAAAA-A")
    assert cid is None
