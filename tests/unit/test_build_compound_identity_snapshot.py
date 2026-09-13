"""Unit tests for the identity-snapshot build script's failure handling.

The live integration test (`test_compound_identity_snapshot_build.py`) proves
real PubChem calls resolve real compounds -- it cannot prove what happens
when PubChem times out or is unreachable *mid-batch*, without actually
waiting for a real outage. This file covers that case offline and
deterministically with `httpx.MockTransport`, matching the convention
already used in `test_downloader.py`.

The property under test, from the module docstring's own claim: "a
per-compound network failure is logged and skipped, never fatal to the whole
batch -- one unreachable compound must not corrupt or discard everything
already resolved."
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from drugsim_chem import process_structure  # noqa: E402

from build_compound_identity_snapshot import _resolve_compounds  # noqa: E402

CAFFEINE_SMILES = "CN1C=NC2=C1C(=O)N(C)C(=O)N2C"
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"

CAFFEINE_INCHIKEY = process_structure(CAFFEINE_SMILES).identity.inchikey_full
ASPIRIN_INCHIKEY = process_structure(ASPIRIN_SMILES).identity.inchikey_full


def _client(transport: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=transport, timeout=10.0)


def _outage_for_one_compound(broken_inchikey: str) -> httpx.MockTransport:
    """A PubChem stand-in that times out for one InChIKey and resolves
    every other request normally, mirroring what an operator would actually
    see: one compound's CID lookup hangs, the rest of the service is up."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url)
        if broken_inchikey in path:
            raise httpx.ConnectTimeout("simulated PubChem outage", request=request)
        if "/cids/JSON" in path:
            return httpx.Response(200, json={"IdentifierList": {"CID": [2519]}})
        if "/property/Title/JSON" in path:
            return httpx.Response(200, json={"PropertyTable": {"Properties": [{"Title": "Caffeine"}]}})
        if "/synonyms/JSON" in path:
            return httpx.Response(200, json={"InformationList": {"Information": [{"Synonym": ["1,3,7-Trimethylxanthine"]}]}})
        if "pug_view" in path:
            return httpx.Response(404)
        raise AssertionError(f"unexpected request in test: {path}")

    return httpx.MockTransport(handler)


class TestExternalIdentityServiceFailure:
    def test_a_timeout_on_one_compound_is_skipped_not_fatal(self) -> None:
        """The exact case the module docstring promises and the live
        integration test cannot exercise: PubChem is unreachable for one
        compound mid-batch."""
        transport = _outage_for_one_compound(ASPIRIN_INCHIKEY)
        with _client(transport) as client:
            compounds, skipped = _resolve_compounds(
                [CAFFEINE_SMILES, ASPIRIN_SMILES], existing={}, client=client, license_spdx="CC0-1.0"
            )

        assert ASPIRIN_SMILES in skipped
        assert CAFFEINE_INCHIKEY in compounds
        assert ASPIRIN_INCHIKEY not in compounds

    def test_the_failed_compound_does_not_corrupt_already_resolved_entries(self) -> None:
        """A prior run's committed entries (the `existing` snapshot) must
        survive a fresh outage on a different, new compound untouched."""
        transport = _outage_for_one_compound(ASPIRIN_INCHIKEY)
        existing = {
            CAFFEINE_INCHIKEY: {
                "inchikey_full": CAFFEINE_INCHIKEY,
                "pubchem_cid": "2519",
                "preferred_name": "Caffeine",
                "synonyms": [],
                "description": None,
                "description_source": None,
                "retrieved_at": "2026-01-01T00:00:00+00:00",
                "license_spdx": "CC0-1.0",
            }
        }
        with _client(transport) as client:
            compounds, skipped = _resolve_compounds(
                [ASPIRIN_SMILES], existing=existing, client=client, license_spdx="CC0-1.0"
            )

        assert compounds[CAFFEINE_INCHIKEY] == existing[CAFFEINE_INCHIKEY]
        assert ASPIRIN_SMILES in skipped
        assert ASPIRIN_INCHIKEY not in compounds

    def test_outage_on_every_compound_yields_an_empty_batch_not_an_exception(self) -> None:
        """A total outage must still return cleanly -- the caller decides
        what to do with an all-skipped batch, the resolver never raises."""

        def all_fail(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("simulated total outage", request=request)

        with _client(httpx.MockTransport(all_fail)) as client:
            compounds, skipped = _resolve_compounds(
                [CAFFEINE_SMILES, ASPIRIN_SMILES], existing={}, client=client, license_spdx="CC0-1.0"
            )

        assert compounds == {}
        assert set(skipped) == {CAFFEINE_SMILES, ASPIRIN_SMILES}

    def test_a_generic_http_error_is_caught_the_same_way_as_a_timeout(self) -> None:
        """Not just timeouts -- any httpx.HTTPError (e.g. a 5xx raised via
        raise_for_status) must be caught by the same per-compound guard."""

        def server_error(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        with _client(httpx.MockTransport(server_error)) as client:
            compounds, skipped = _resolve_compounds(
                [CAFFEINE_SMILES], existing={}, client=client, license_spdx="CC0-1.0"
            )

        assert compounds == {}
        assert skipped == [CAFFEINE_SMILES]
