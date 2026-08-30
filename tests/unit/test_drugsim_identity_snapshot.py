"""Tests for the offline compound-identity snapshot loader/resolver.

No network, no model artifact -- these exercise only the pure, in-memory
lookup logic the live `/predict` path actually calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drugsim_identity import CompoundIdentityRecord, load_identity_snapshot, resolve_identity

pytestmark = pytest.mark.unit

CAFFEINE_INCHIKEY = "RYYVLZVUVIJVGH-UHFFFAOYSA-N"


def _write_snapshot(tmp_path: Path, compounds: list[dict]) -> Path:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"compounds": compounds}), encoding="utf-8")
    return path


class TestLoadIdentitySnapshot:
    def test_missing_file_returns_empty_dict(self, tmp_path: Path) -> None:
        assert load_identity_snapshot(tmp_path / "does_not_exist.json") == {}

    def test_loads_and_keys_by_inchikey(self, tmp_path: Path) -> None:
        path = _write_snapshot(
            tmp_path,
            [
                {
                    "inchikey_full": CAFFEINE_INCHIKEY,
                    "pubchem_cid": "2519",
                    "preferred_name": "Caffeine",
                    "synonyms": ["1,3,7-Trimethylxanthine"],
                    "description": "A central nervous system stimulant of the methylxanthine class.",
                    "description_source": "PubChem (ChEBI)",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "license_spdx": "US-PD",
                }
            ],
        )
        snapshot = load_identity_snapshot(path)
        assert set(snapshot) == {CAFFEINE_INCHIKEY}
        record = snapshot[CAFFEINE_INCHIKEY]
        assert isinstance(record, CompoundIdentityRecord)
        assert record.preferred_name == "Caffeine"
        assert record.synonyms == ("1,3,7-Trimethylxanthine",)

    def test_missing_optional_fields_default_sensibly(self, tmp_path: Path) -> None:
        path = _write_snapshot(
            tmp_path,
            [
                {
                    "inchikey_full": CAFFEINE_INCHIKEY,
                    "pubchem_cid": "2519",
                    "preferred_name": "Caffeine",
                    "retrieved_at": "2026-01-01T00:00:00+00:00",
                    "license_spdx": "US-PD",
                    # synonyms, description, description_source omitted
                }
            ],
        )
        record = load_identity_snapshot(path)[CAFFEINE_INCHIKEY]
        assert record.synonyms == ()
        assert record.description is None
        assert record.description_source is None


class TestResolveIdentity:
    def test_known_inchikey_resolves_identified(self) -> None:
        snapshot = {
            CAFFEINE_INCHIKEY: CompoundIdentityRecord(
                inchikey_full=CAFFEINE_INCHIKEY,
                pubchem_cid="2519",
                preferred_name="Caffeine",
                synonyms=("1,3,7-Trimethylxanthine", "Guaranine"),
                description="A central nervous system stimulant.",
                description_source="PubChem (ChEBI)",
                retrieved_at="2026-01-01T00:00:00+00:00",
                license_spdx="US-PD",
            )
        }
        result = resolve_identity(CAFFEINE_INCHIKEY, snapshot)
        assert result.identity_status == "identified"
        assert result.compound_name == "Caffeine"
        assert result.synonyms == ("1,3,7-Trimethylxanthine", "Guaranine")
        assert result.identifiers == {"pubchem_cid": "2519"}
        assert result.description == "A central nervous system stimulant."
        assert result.description_source == "PubChem (ChEBI)"
        assert result.source == "PubChem"
        assert result.retrieved_at == "2026-01-01T00:00:00+00:00"

    def test_unknown_inchikey_resolves_unidentified_with_every_other_field_none(self) -> None:
        result = resolve_identity("NOVEL-MADE-UP-KEY", {})
        assert result.identity_status == "unidentified"
        assert result.compound_name is None
        assert result.synonyms is None
        assert result.identifiers is None
        assert result.description is None
        assert result.description_source is None
        assert result.source is None
        assert result.retrieved_at is None

    def test_identified_record_missing_a_description_gets_the_placeholder_string(self) -> None:
        """A compound found in PubChem but with no PUG-View description on
        record must never be silently blank -- and never invented."""
        snapshot = {
            CAFFEINE_INCHIKEY: CompoundIdentityRecord(
                inchikey_full=CAFFEINE_INCHIKEY,
                pubchem_cid="2519",
                preferred_name="Caffeine",
                synonyms=(),
                description=None,
                description_source=None,
                retrieved_at="2026-01-01T00:00:00+00:00",
                license_spdx="US-PD",
            )
        }
        result = resolve_identity(CAFFEINE_INCHIKEY, snapshot)
        assert result.identity_status == "identified"
        assert result.description == "Verified description unavailable."
        assert result.description_source is None

    def test_empty_synonyms_tuple_becomes_none_not_empty_list(self) -> None:
        """A resolved-but-synonym-less compound should not render an empty
        'Synonyms' section in the UI -- None is the signal to omit it."""
        snapshot = {
            CAFFEINE_INCHIKEY: CompoundIdentityRecord(
                inchikey_full=CAFFEINE_INCHIKEY,
                pubchem_cid="2519",
                preferred_name="Caffeine",
                synonyms=(),
                description="A stimulant.",
                description_source="PubChem",
                retrieved_at="2026-01-01T00:00:00+00:00",
                license_spdx="US-PD",
            )
        }
        result = resolve_identity(CAFFEINE_INCHIKEY, snapshot)
        assert result.synonyms is None
