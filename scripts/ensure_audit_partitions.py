#!/usr/bin/env python3
"""Ensure monthly range partitions exist for audit_log ahead of need.

audit_log ships with a DEFAULT partition only (database/ddl/02_governance.sql),
so inserts never fail for lack of a partition — but everything lands in the
default partition until explicit monthly ranges exist, which defeats the point
of partitioning (query pruning, easier archival). This script creates the
current month's partition plus a configurable number of months ahead.

Intended to run on a schedule (cron, or a Dagster sensor once Dagster exists) —
this is the operational task flagged in Phase 1 Step 3 §12 known gap #5 and in
the DDL comment on audit_log_default. It is idempotent: existing partitions are
left alone.

Usage:
    python scripts/ensure_audit_partitions.py [--months-ahead N]
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from drugsim_core.logging import configure_logging, get_logger  # noqa: E402
from drugsim_db.engine import get_engine  # noqa: E402


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the [start, end) date bounds for a given month."""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def ensure_partition(engine: object, year: int, month: int) -> bool:
    """Create the audit_log partition for one month if it does not already exist.

    Args:
        engine: A SQLAlchemy engine.
        year: Calendar year.
        month: Calendar month (1-12).

    Returns:
        True if a new partition was created, False if it already existed.
    """
    start, end = _month_bounds(year, month)
    partition_name = f"audit_log_{year:04d}_{month:02d}"

    with engine.connect() as conn:  # type: ignore[attr-defined]
        exists = conn.execute(
            text("SELECT 1 FROM pg_class WHERE relname = :name"), {"name": partition_name}
        ).first()
        if exists:
            return False

        conn.execute(
            text(
                f"CREATE TABLE {partition_name} PARTITION OF audit_log "  # noqa: S608
                "FOR VALUES FROM (:start) TO (:end)"
            ),
            {"start": start, "end": end},
        )
        conn.commit()
        return True


def main() -> int:
    """Create current-month and upcoming audit_log partitions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months-ahead", type=int, default=3, help="Months beyond the current one to pre-create."
    )
    args = parser.parse_args()

    configure_logging()
    logger = get_logger(__name__)
    engine = get_engine()

    # datetime.now(timezone.utc).date(), not date.today(): consistent with the
    # "always UTC, always timezone-aware" convention established in Sprint 2.1
    # (ruff rule DTZ). timezone.utc rather than the datetime.UTC alias (3.11+)
    # for compatibility with older Python during local verification; both name
    # the identical tzinfo object.
    today = datetime.now(timezone.utc).date()
    created = []
    for offset in range(args.months_ahead + 1):
        month_index = today.month - 1 + offset
        year = today.year + month_index // 12
        month = month_index % 12 + 1
        if ensure_partition(engine, year, month):
            created.append(f"{year:04d}-{month:02d}")

    if created:
        logger.info("audit_log partitions created", months=created)
    else:
        logger.info("audit_log partitions already current, nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
