#!/usr/bin/env python3
"""Back up the prediction audit-log SQLite database.

Phase 8 Sec 12. Uses SQLite's own online backup API (not a raw file copy),
so a backup taken while the service is running and writing never captures
a half-written page. Writes a SHA-256 checksum sidecar and verifies the
backup by re-opening it and counting rows -- per the brief's own words,
"do not consider a backup successful merely because a backup command
completed."

Usage:
    python scripts/backup_predictions_db.py [--db PATH] [--dest-dir DIR]

Retention and storage location are operational decisions made at deploy
time (see docs/phase8/phase8-deployment-report.md "Backups" for the
documented policy); this script performs one backup and verifies it, it
does not implement scheduling or off-host upload itself -- wire it into
cron/a scheduled job/CI with whatever off-host destination the deployment
uses (S3, a backup volume, etc).
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drugsim_predict.settings import get_predict_settings  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_database(db_path: Path, dest_dir: Path) -> Path:
    """Perform an online, consistent backup and verify it.

    Args:
        db_path: The live database to back up.
        dest_dir: Directory to write the timestamped backup into.

    Returns:
        Path to the verified backup file.

    Raises:
        FileNotFoundError: If ``db_path`` does not exist.
        RuntimeError: If the backup cannot be verified (row count mismatch,
            or the backup file cannot be opened at all).
    """
    if not db_path.exists():
        msg = f"source database does not exist: {db_path}"
        raise FileNotFoundError(msg)

    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = dest_dir / f"predictions-{timestamp}.sqlite3"

    source_conn = sqlite3.connect(str(db_path))
    try:
        source_row_count = source_conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        dest_conn = sqlite3.connect(str(backup_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        source_conn.close()

    # Verify: the backup must be independently openable and contain the
    # same row count observed in the source at backup time. A backup file
    # that "completed" but cannot be read back is not a successful backup.
    verify_conn = sqlite3.connect(str(backup_path))
    try:
        backup_row_count = verify_conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        msg = f"backup verification failed: could not query {backup_path}: {exc}"
        raise RuntimeError(msg) from exc
    finally:
        verify_conn.close()

    if backup_row_count != source_row_count:
        msg = f"backup verification failed: source had {source_row_count} rows, backup has {backup_row_count}"
        raise RuntimeError(msg)

    checksum = _sha256(backup_path)
    (backup_path.with_suffix(backup_path.suffix + ".sha256")).write_text(f"{checksum}  {backup_path.name}\n")

    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=None, help="Path to the live predictions.sqlite3 (default: configured path)")
    parser.add_argument("--dest-dir", type=Path, default=Path("var/backups"), help="Directory to write the backup into")
    args = parser.parse_args()

    db_path = args.db or get_predict_settings().prediction_db_path

    try:
        backup_path = backup_database(db_path, args.dest_dir)
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Backup verified and written to {backup_path}")
    print(f"Checksum: {backup_path.with_suffix(backup_path.suffix + '.sha256').read_text().strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
