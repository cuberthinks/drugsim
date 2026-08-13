"""Record a completed download as an ``ingestion_snapshot`` row.

Closes the loop from Sprint 2.4's download/checksum/landing mechanics to the
provenance table those bytes must be recorded in — a downloaded, landed,
verified file that never becomes a queryable snapshot row is invisible to
everything downstream (ETL, licence audit, reproducibility).

Split the same way as ``registry_sync``: :func:`build_snapshot_record` is pure
(computes the row, including the derived ``snapshot_id``) and is what
``tests/unit/test_snapshots_db.py`` exercises without a database;
:func:`record_ingestion_snapshot` is the thin insert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_ingest.snapshot import build_snapshot_id

__all__ = ["build_snapshot_record", "record_ingestion_snapshot"]


def build_snapshot_record(
    *,
    source_id: str,
    source_version: str,
    acquired_at: datetime,
    content_sha256: str,
    byte_size: int,
    landing_uri: str,
    license_at_time: str,
    record_count: Optional[int] = None,
) -> dict[str, Any]:
    """Compute the ``ingestion_snapshot`` row for a completed download.

    Pure function: the ``snapshot_id`` is derived deterministically from its
    inputs (:func:`drugsim_ingest.snapshot.build_snapshot_id`), so calling this
    twice with identical inputs produces an identical row — which is exactly
    what should happen if the same content is (re-)landed, and is what lets
    the landing zone's write-once guard (:class:`ImmutabilityViolationError`)
    catch an accidental re-run rather than silently create a second snapshot
    for the same bytes.

    Args:
        source_id: Registry source id.
        source_version: Upstream version string, e.g. ``chembl_37``.
        acquired_at: When the download completed.
        content_sha256: Full digest of the downloaded content.
        byte_size: Total bytes downloaded.
        landing_uri: Where the bytes were written in Z1 (e.g.
            ``s3://drugsim-z1-landing/{key}``).
        license_at_time: The licence as it stood at acquisition (Phase 1: kept
            separate from the registry's current value so a later relicensing
            does not retroactively change the terms this snapshot was taken
            under).
        record_count: Row/entry count if known at acquisition time; often
            unknown until parsing (Sprint 2.5) and left ``None`` here.

    Returns:
        A dict of column values ready to bind into an INSERT.
    """
    snapshot_id = build_snapshot_id(source_version, acquired_at, content_sha256)
    return {
        "snapshot_id": snapshot_id,
        "source_id": source_id,
        "source_version": source_version,
        "acquired_at": acquired_at,
        "content_sha256": content_sha256,
        "byte_size": byte_size,
        "record_count": record_count,
        "landing_uri": landing_uri,
        "license_at_time": license_at_time,
    }


def record_ingestion_snapshot(session: Session, fields: dict[str, Any]) -> str:
    """Insert an ``ingestion_snapshot`` row.

    Args:
        session: An active session.
        fields: From :func:`build_snapshot_record`.

    Returns:
        The snapshot id.
    """
    session.execute(
        text(
            "INSERT INTO ingestion_snapshot (snapshot_id, source_id, "
            "source_version, acquired_at, content_sha256, byte_size, "
            "record_count, landing_uri, license_at_time) "
            "VALUES (:snapshot_id, :source_id, :source_version, :acquired_at, "
            ":content_sha256, :byte_size, :record_count, :landing_uri, "
            ":license_at_time)"
        ),
        fields,
    )
    return str(fields["snapshot_id"])
