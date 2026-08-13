"""Tests for the Z1 snapshot id and landing-key naming convention."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from drugsim_ingest.snapshot import build_landing_key, build_snapshot_id, parse_snapshot_id

pytestmark = pytest.mark.unit


class TestBuildSnapshotId:
    """Matches Phase 1 Step 2 §3's convention exactly."""

    def test_matches_the_documented_format(self) -> None:
        acquired = datetime(2026, 6, 14, tzinfo=timezone.utc)
        snapshot_id = build_snapshot_id("chembl_37", acquired, "a3f9c21b8e40d1f2a3b4c5d6e7f8091a")
        assert snapshot_id == "chembl_37__2026-06-14__a3f9c21b8e40"

    def test_sha_is_lowercased(self) -> None:
        acquired = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot_id = build_snapshot_id("x", acquired, "ABCDEF012345" + "0" * 20)
        assert snapshot_id.endswith("abcdef012345")

    def test_double_underscore_in_source_version_rejected(self) -> None:
        """Would make the id ambiguous to parse back apart."""
        with pytest.raises(ValueError, match="must not contain"):
            build_snapshot_id("bad__version", datetime.now(timezone.utc), "a" * 64)

    def test_short_sha_rejected(self) -> None:
        with pytest.raises(ValueError, match="too short"):
            build_snapshot_id("x", datetime.now(timezone.utc), "abc")

    def test_only_date_embedded_not_time(self) -> None:
        """Two acquisitions on the same day produce ids differing only by
        checksum, not by time-of-day — same-day re-runs against unchanged
        upstream content are meant to collide (Z1 immutability catches it)."""
        morning = datetime(2026, 6, 14, 3, 0, 0, tzinfo=timezone.utc)
        evening = datetime(2026, 6, 14, 23, 0, 0, tzinfo=timezone.utc)
        same_sha = "a" * 64
        assert build_snapshot_id("x", morning, same_sha) == build_snapshot_id("x", evening, same_sha)


class TestParseSnapshotId:
    """Round-trip and rejection of malformed ids."""

    def test_roundtrips_the_components(self) -> None:
        acquired = datetime(2026, 6, 14, tzinfo=timezone.utc)
        snapshot_id = build_snapshot_id("chembl_37", acquired, "a3f9c21b8e40" + "0" * 20)
        source_version, acquired_date, sha_prefix = parse_snapshot_id(snapshot_id)
        assert source_version == "chembl_37"
        assert acquired_date == acquired.date()
        assert sha_prefix == "a3f9c21b8e40"

    @pytest.mark.parametrize(
        "bad",
        ["", "no-separators", "a__2026-13-40__abc", "a__2026-06-14__NOTHEX0000000"],
    )
    def test_malformed_ids_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError, match="malformed snapshot_id|day is out of range|month must be"):
            parse_snapshot_id(bad)


class TestBuildLandingKey:
    """Z1 object key layout."""

    def test_matches_the_documented_layout(self) -> None:
        key = build_landing_key("red", "chembl", "chembl_37__2026-06-14__a3f9c21b8e40", "activities.parquet")
        assert key == "red/chembl/chembl_37__2026-06-14__a3f9c21b8e40/activities.parquet"

    @pytest.mark.parametrize("field", ["license_tier", "source_id", "snapshot_id"])
    def test_slash_in_any_component_rejected(self, field: str) -> None:
        kwargs = {"license_tier": "red", "source_id": "x", "snapshot_id": "y", "filename": "f.txt"}
        kwargs[field] = "bad/value"
        with pytest.raises(ValueError, match="must not contain '/'"):
            build_landing_key(**kwargs)

    def test_filename_may_contain_no_slash_restriction(self) -> None:
        """Filenames are user-facing and preserved as-is; only the structural
        components are restricted."""
        key = build_landing_key("green", "pdb", "snap1", "1CRN.pdb")
        assert key.endswith("1CRN.pdb")
