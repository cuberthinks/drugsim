"""Pure logic for Z1 snapshot identifiers and landing-zone key layout.

Kept separate from any I/O so the naming convention — which other code and
humans will come to rely on for object-storage layout — is exercised by plain
unit tests, no mock services required.
"""

from __future__ import annotations

import re
from datetime import date, datetime

__all__ = ["build_landing_key", "build_snapshot_id", "parse_snapshot_id"]

_SNAPSHOT_ID_RE = re.compile(
    r"^(?P<source_version>.+)__(?P<acquired_date>\d{4}-\d{2}-\d{2})__(?P<sha_prefix>[a-f0-9]{12})$"
)


def build_snapshot_id(
    source_version: str,
    acquired_at: datetime,
    content_sha256: str,
) -> str:
    """Build a snapshot identifier: ``{source_version}__{date}__{sha256[:12]}``.

    Matches Phase 1 Step 2 §3's Z1 naming convention exactly, so existing
    documentation and any tooling built against that convention are not
    silently invalidated by a different implementation.

    Args:
        source_version: Upstream version string, e.g. ``chembl_37``.
        acquired_at: When the snapshot was taken. Only the date is embedded —
            multiple acquisitions on the same day are disambiguated by the
            checksum suffix, not by time-of-day, since re-running an ingest
            twice in one day against unchanged upstream content should ideally
            collide (and be caught by :class:`ImmutabilityViolationError`)
            rather than silently create two near-duplicate snapshots.
        content_sha256: Full hex digest of the acquired content.

    Returns:
        The snapshot id, e.g. ``chembl_37__2026-06-14__a3f9c21b8e40``.

    Raises:
        ValueError: If ``source_version`` contains the ``__`` separator, which
            would make the id ambiguous to parse back apart.
        ValueError: If ``content_sha256`` is too short to take a 12-char prefix.
    """
    if "__" in source_version:
        msg = f"source_version must not contain '__': {source_version!r}"
        raise ValueError(msg)
    if len(content_sha256) < 12:
        msg = f"content_sha256 too short to derive a 12-char prefix: {content_sha256!r}"
        raise ValueError(msg)

    acquired_date = acquired_at.date().isoformat()
    return f"{source_version}__{acquired_date}__{content_sha256[:12].lower()}"


def parse_snapshot_id(snapshot_id: str) -> tuple[str, date, str]:
    """Parse a snapshot id back into its components.

    Args:
        snapshot_id: A value produced by :func:`build_snapshot_id`.

    Returns:
        ``(source_version, acquired_date, sha_prefix)``.

    Raises:
        ValueError: If ``snapshot_id`` does not match the expected format.
    """
    match = _SNAPSHOT_ID_RE.match(snapshot_id)
    if match is None:
        msg = f"malformed snapshot_id: {snapshot_id!r}"
        raise ValueError(msg)
    return (
        match.group("source_version"),
        date.fromisoformat(match.group("acquired_date")),
        match.group("sha_prefix"),
    )


def build_landing_key(
    license_tier: str,
    source_id: str,
    snapshot_id: str,
    filename: str,
) -> str:
    """Build a Z1 object key: ``{license_tier}/{source_id}/{snapshot_id}/{filename}``.

    Args:
        license_tier: One of ``green``, ``amber``, ``red``, ``black``.
        source_id: Registry source id, e.g. ``chembl``.
        snapshot_id: From :func:`build_snapshot_id`.
        filename: The file's own name, preserved as-is so a human browsing the
            bucket recognises it.

    Returns:
        The full object key.

    Raises:
        ValueError: If any component contains a ``/``, which would corrupt the
            key structure this function exists to guarantee.
    """
    for label, value in (
        ("license_tier", license_tier),
        ("source_id", source_id),
        ("snapshot_id", snapshot_id),
    ):
        if "/" in value:
            msg = f"{label} must not contain '/': {value!r}"
            raise ValueError(msg)
    return f"{license_tier}/{source_id}/{snapshot_id}/{filename}"
