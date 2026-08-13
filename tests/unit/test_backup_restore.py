"""Tests for the Phase 8 prediction-database backup/restore scripts.

These pin the exact end-to-end cycle manually verified while building the
scripts (docs/phase8/phase8-deployment-report.md "Backups"): a backup must
be independently verifiable, a restore must refuse an unverifiable or
corrupted backup, and a successful restore must recover the real data, not
just a matching row count.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from backup_predictions_db import backup_database  # noqa: E402
from restore_predictions_db import restore_database  # noqa: E402

from drugsim_predict.store import PredictionStore  # noqa: E402

pytestmark = pytest.mark.unit


def _seeded_store(db_path: Path, n: int = 5, prefix: str = "prd_test") -> None:
    store = PredictionStore(db_path=db_path)
    for i in range(n):
        store.record_success(
            prediction_id=f"{prefix}{i}", request_id=f"req_test{i}", created_at="2026-08-09T00:00:00",
            model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1", feature_set_id="fake",
            input_hash=f"hash{i}", canonical_structure_hash=f"canon{i}",
            applicability_domain_verdict="in_domain", predicted_label="non_blocker",
            predicted_probability_blocker=0.1, response_json="{}",
        )


class TestBackupAndRestore:
    def test_backup_is_created_and_verified(self, tmp_path: Path) -> None:
        live_db = tmp_path / "predictions.sqlite3"
        _seeded_store(live_db)

        backup_path = backup_database(live_db, tmp_path / "backups")

        assert backup_path.exists()
        assert backup_path.with_suffix(backup_path.suffix + ".sha256").exists()

    def test_backup_of_missing_database_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            backup_database(tmp_path / "does_not_exist.sqlite3", tmp_path / "backups")

    def test_full_disaster_recovery_cycle(self, tmp_path: Path) -> None:
        """Backup -> delete the live database -> restore -> verify content
        (not just row count) matches exactly. The literal scenario Sec 12
        asks be tested at least once."""
        live_db = tmp_path / "predictions.sqlite3"
        _seeded_store(live_db, n=5)

        backup_path = backup_database(live_db, tmp_path / "backups")
        live_db.unlink()
        assert not live_db.exists()

        row_count = restore_database(backup_path, live_db)
        assert row_count == 5

        restored = PredictionStore(db_path=live_db)
        row = restored.get("prd_test3")
        assert row is not None
        assert row["predicted_label"] == "non_blocker"
        assert row["input_hash"] == "hash3"

    def test_restore_rejects_corrupted_backup(self, tmp_path: Path) -> None:
        live_db = tmp_path / "predictions.sqlite3"
        _seeded_store(live_db)
        backup_path = backup_database(live_db, tmp_path / "backups")

        with open(backup_path, "r+b") as f:
            f.seek(100)
            f.write(b"\x00\x00\x00\x00")

        with pytest.raises(ValueError, match="checksum mismatch"):
            restore_database(backup_path, live_db)

    def test_restore_rejects_backup_without_checksum_sidecar(self, tmp_path: Path) -> None:
        fake_backup = tmp_path / "no_checksum.sqlite3"
        fake_backup.write_bytes(b"not a real sqlite file")

        with pytest.raises(FileNotFoundError, match="checksum sidecar"):
            restore_database(fake_backup, tmp_path / "predictions.sqlite3", force=True)

    def test_restore_refuses_to_overwrite_without_force(self, tmp_path: Path) -> None:
        live_db = tmp_path / "predictions.sqlite3"
        _seeded_store(live_db)
        backup_path = backup_database(live_db, tmp_path / "backups")

        with pytest.raises(ValueError, match="already exists"):
            restore_database(backup_path, live_db, force=False)

    def test_restore_preserves_prior_file_as_pre_restore_copy(self, tmp_path: Path) -> None:
        live_db = tmp_path / "predictions.sqlite3"
        _seeded_store(live_db, n=1)
        backup_path = backup_database(live_db, tmp_path / "backups")

        _seeded_store(live_db, n=3, prefix="prd_after_backup")  # different content than the backup
        restore_database(backup_path, live_db, force=True)

        pre_restore = Path(str(live_db) + ".pre-restore")
        assert pre_restore.exists()
