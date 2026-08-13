"""Tests for the pure ingestion_snapshot row-building logic.

No database — record_ingestion_snapshot's actual INSERT is exercised at
tests/constraints/test_registry_sync_integration.py-style integration tests
(deferred; needs Docker). This file covers build_snapshot_record, which is
where a real bug would hide: the derived snapshot_id and the field mapping.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from drugsim_db.snapshots import build_snapshot_record

pytestmark = pytest.mark.unit


class TestBuildSnapshotRecord:
    """Field mapping and derived snapshot_id correctness."""

    def test_derives_the_documented_snapshot_id_format(self) -> None:
        record = build_snapshot_record(
            source_id="chembl",
            source_version="chembl_37",
            acquired_at=datetime(2026, 6, 14, tzinfo=timezone.utc),
            content_sha256="a3f9c21b8e40" + "0" * 20,
            byte_size=1234,
            landing_uri="s3://drugsim-z1-landing/red/chembl/x/y.tar.gz",
            license_at_time="CC-BY-SA-3.0",
        )
        assert record["snapshot_id"] == "chembl_37__2026-06-14__a3f9c21b8e40"

    def test_identical_inputs_produce_an_identical_record(self) -> None:
        """A prerequisite for the landing zone's write-once guard to correctly
        catch an accidental re-run: the same content must derive the same
        snapshot_id, not a fresh one each time."""
        kwargs = {
            "source_id": "pdb",
            "source_version": "weekly-2026-06-14",
            "acquired_at": datetime(2026, 6, 14, tzinfo=timezone.utc),
            "content_sha256": "b" * 64,
            "byte_size": 500,
            "landing_uri": "s3://x/y",
            "license_at_time": "CC0-1.0",
        }
        assert build_snapshot_record(**kwargs) == build_snapshot_record(**kwargs)

    def test_record_count_defaults_to_none(self) -> None:
        record = build_snapshot_record(
            source_id="x", source_version="v1", acquired_at=datetime.now(timezone.utc),
            content_sha256="c" * 64, byte_size=1, landing_uri="s3://x/y", license_at_time="CC0-1.0",
        )
        assert record["record_count"] is None

    def test_record_count_passed_through_when_known(self) -> None:
        record = build_snapshot_record(
            source_id="x", source_version="v1", acquired_at=datetime.now(timezone.utc),
            content_sha256="c" * 64, byte_size=1, landing_uri="s3://x/y", license_at_time="CC0-1.0",
            record_count=42,
        )
        assert record["record_count"] == 42

    def test_license_at_time_is_independent_of_current_registry_state(self) -> None:
        """This field intentionally has no cross-check against data_source's
        current license_spdx — it is a point-in-time record, and a later
        relicensing must not retroactively alter it."""
        record = build_snapshot_record(
            source_id="x", source_version="v1", acquired_at=datetime.now(timezone.utc),
            content_sha256="c" * 64, byte_size=1, landing_uri="s3://x/y",
            license_at_time="CC-BY-SA-4.0",
        )
        assert record["license_at_time"] == "CC-BY-SA-4.0"

    def test_all_required_columns_present(self) -> None:
        record = build_snapshot_record(
            source_id="x", source_version="v1", acquired_at=datetime.now(timezone.utc),
            content_sha256="c" * 64, byte_size=1, landing_uri="s3://x/y", license_at_time="CC0-1.0",
        )
        expected_columns = {
            "snapshot_id", "source_id", "source_version", "acquired_at",
            "content_sha256", "byte_size", "record_count", "landing_uri",
            "license_at_time",
        }
        assert set(record) == expected_columns
