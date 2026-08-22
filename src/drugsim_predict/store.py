"""Provenance log for every prediction request — accepted or rejected.

Every call to :meth:`PredictionStore.record_success` or
:meth:`PredictionStore.record_rejection` is one atomic transaction: either
the full row is written or nothing is (SQLite's default transactional
behaviour, used explicitly here rather than relied on implicitly). A
prediction is never "half logged."

**Redaction boundary**: this store is the tenant-scoped "database row" TDS
Sec 6.6.1 describes ("the structure lives only in the tenant-scoped
database row") — it legitimately holds the full canonical structure, because
retrieving ``GET /predict/{id}`` must be able to show a caller their own
molecule back. What must NEVER contain the raw structure is the
*application log stream* (structlog), which is a separate, wider-fanout
system (TDS Sec 7, P11) — callers in :mod:`drugsim_predict.api` log with
:func:`drugsim_core.redaction.structure_digest`, never the raw SMILES.

**Retrieval scoping** (confidentiality audit, 2026-08-22 finding #1): a row
records ``api_key_hash`` — a SHA-256 digest of the API key that created it,
never the raw key — so :mod:`drugsim_predict.api`'s ``GET /predict/{id}``
handler can require the retrieving caller's key to match the creating
caller's key before returning ``response_json``. Before this column
existed, any caller holding any one configured API key could retrieve any
other caller's stored prediction (including their canonical structure) by
ID, because this store had no notion of who a row belonged to. ``ALTER
TABLE ... ADD COLUMN`` in :meth:`_init_schema` migrates an existing
database file in place; a row written before this change (or written while
no API key was configured, e.g. local/dev) has ``api_key_hash IS NULL`` and
is therefore retrievable by no one once key auth is active — fail closed,
not open, for data this store cannot attribute to a caller.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from drugsim_predict.settings import get_predict_settings

__all__ = ["PredictionStore"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    model_id TEXT,
    model_version TEXT,
    dataset_version TEXT,
    feature_set_id TEXT,
    input_hash TEXT NOT NULL,
    canonical_structure_hash TEXT,
    validation_status TEXT NOT NULL,
    rejection_reason TEXT,
    applicability_domain_verdict TEXT,
    predicted_label TEXT,
    predicted_probability_blocker REAL,
    final_prediction_status TEXT NOT NULL,
    response_json TEXT,
    api_key_hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_predictions_request_id ON predictions(request_id);
CREATE INDEX IF NOT EXISTS ix_predictions_created_at ON predictions(created_at);
"""


class PredictionStore:
    """SQLite-backed prediction provenance log.

    Args:
        db_path: Override the configured database file (mainly for tests,
            e.g. an in-memory ``:memory:`` database or a temp file).
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or get_predict_settings().prediction_db_path
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # Migrates a database file created before api_key_hash existed
            # (in place, idempotent) -- CREATE TABLE IF NOT EXISTS above is a
            # no-op against an existing table, so an already-deployed
            # var/predictions.sqlite3 needs this explicit ALTER TABLE to
            # pick up the column at all.
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(predictions)")}
            if "api_key_hash" not in existing_columns:
                conn.execute("ALTER TABLE predictions ADD COLUMN api_key_hash TEXT")
            conn.commit()

    def record_success(
        self,
        *,
        prediction_id: str,
        request_id: str,
        created_at: str,
        model_id: str,
        model_version: str,
        dataset_version: str,
        feature_set_id: str,
        input_hash: str,
        canonical_structure_hash: str,
        applicability_domain_verdict: str,
        predicted_label: str,
        predicted_probability_blocker: float,
        response_json: str,
        api_key_hash: Optional[str] = None,
    ) -> None:
        """Record a completed, successful prediction. One atomic write.

        Args:
            api_key_hash: SHA-256 digest of the API key that made this
                request (see :mod:`drugsim_predict.security`), or ``None``
                when no key auth is configured. Gates ``GET /predict/{id}``
                retrieval -- see this module's docstring.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO predictions (
                        id, request_id, created_at, model_id, model_version, dataset_version,
                        feature_set_id, input_hash, canonical_structure_hash, validation_status,
                        rejection_reason, applicability_domain_verdict, predicted_label,
                        predicted_probability_blocker, final_prediction_status, response_json,
                        api_key_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted', NULL, ?, ?, ?, 'complete', ?, ?)
                    """,
                    (
                        prediction_id, request_id, created_at, model_id, model_version, dataset_version,
                        feature_set_id, input_hash, canonical_structure_hash,
                        applicability_domain_verdict, predicted_label, predicted_probability_blocker,
                        response_json, api_key_hash,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_rejection(
        self,
        *,
        prediction_id: str,
        request_id: str,
        created_at: str,
        input_hash: str,
        rejection_reason: str,
    ) -> None:
        """Record a rejected (invalid-structure or reproducibility-failure)
        request. Still logged — a rejection is provenance too."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO predictions (
                        id, request_id, created_at, model_id, model_version, dataset_version,
                        feature_set_id, input_hash, canonical_structure_hash, validation_status,
                        rejection_reason, applicability_domain_verdict, predicted_label,
                        predicted_probability_blocker, final_prediction_status, response_json
                    ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, ?, NULL, 'rejected', ?, NULL, NULL, NULL, 'failed', NULL)
                    """,
                    (prediction_id, request_id, created_at, input_hash, rejection_reason),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def ping(self) -> bool:
        """Cheap reachability/writability check for health endpoints.

        Returns:
            True if the database file can be opened and queried.

        Raises:
            sqlite3.Error: If the database cannot be reached at all -- left
                to propagate rather than swallowed, so the caller (a health
                check) can log the real cause server-side while returning a
                generic status publicly.
        """
        with self._connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True

    def get(self, prediction_id: str) -> Optional[dict]:
        """Retrieve one prediction record by its public ID.

        Returns:
            A dict of the stored row, or ``None`` if no such prediction
            exists. ``response_json`` is returned as the raw string (the
            caller parses it) so this method has no dependency on the
            response schema.
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
            return dict(row) if row is not None else None
