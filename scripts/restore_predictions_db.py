#!/usr/bin/env python3
"""Restore the prediction audit-log database from a verified backup.

Phase 8 Sec 12. Verifies the backup's checksum sidecar before touching
anything, refuses to overwrite a live database without an explicit
--force, and moves (never deletes) whatever was at the destination to a
``.pre-restore`` sidecar first, so a bad restore is itself recoverable.

Usage:
    python scripts/restore_predictions_db.py --backup PATH [--dest PATH] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drugsim_predict.settings import get_predict_settings  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_database(backup_path: Path, dest_path: Path, *, force: bool = False) -> int:
    """Restore ``backup_path`` to ``dest_path`` after verifying its checksum.

    Returns:
        The row count found in the restored database.

    Raises:
        FileNotFoundError: If the backup or its checksum sidecar is missing.
        ValueError: If the checksum does not match, or the destination
            already exists and ``force`` is not set.
        RuntimeError: If the restored file cannot be opened/queried.
    """
    if not backup_path.exists():
        msg = f"backup file does not exist: {backup_path}"
        raise FileNotFoundError(msg)

    checksum_path = backup_path.with_suffix(backup_path.suffix + ".sha256")
    if not checksum_path.exists():
        msg = f"no checksum sidecar found for {backup_path} -- refusing to restore an unverifiable backup"
        raise FileNotFoundError(msg)

    expected = checksum_path.read_text().split()[0]
    actual = _sha256(backup_path)
    if actual != expected:
        msg = f"checksum mismatch: backup file may be corrupted (expected {expected}, got {actual})"
        raise ValueError(msg)

    if dest_path.exists() and not force:
        msg = f"{dest_path} already exists -- pass --force to replace it (the existing file is preserved as a .pre-restore copy either way)"
        raise ValueError(msg)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        shutil.move(str(dest_path), str(dest_path) + ".pre-restore")

    shutil.copy2(str(backup_path), str(dest_path))

    verify_conn = sqlite3.connect(str(dest_path))
    try:
        row_count = verify_conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        msg = f"restored file failed verification: {exc}"
        raise RuntimeError(msg) from exc
    finally:
        verify_conn.close()

    return row_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True, help="Path to the backup .sqlite3 file")
    parser.add_argument("--dest", type=Path, default=None, help="Restore destination (default: configured live path)")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing destination file")
    args = parser.parse_args()

    dest_path = args.dest or get_predict_settings().prediction_db_path

    try:
        row_count = restore_database(args.backup, dest_path, force=args.force)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"RESTORE FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"Restored {args.backup} to {dest_path}")
    print(f"Verified: {row_count} rows readable in the restored database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
