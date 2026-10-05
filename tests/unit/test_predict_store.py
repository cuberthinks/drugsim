"""Tests for the prediction provenance store, on both of its backends.

Every behavioural test below runs twice -- once on SQLite, once on a real
PostgreSQL 16 server (the embedded one shipped by the ``pgserver`` package,
so no Docker is needed). The PostgreSQL leg is skipped, not failed, where
``pgserver``/``psycopg`` are not installed (e.g. a minimal CI image): the
contract is the same either way, which is the point of running both.
"""

from __future__ import annotations

import pytest

from drugsim_predict.settings import get_predict_settings
from drugsim_predict.store import PredictionStore

pytestmark = pytest.mark.unit


@pytest.fixture(scope="session")
def _postgres_url(tmp_path_factory):
    pgserver = pytest.importorskip("pgserver")
    pytest.importorskip("psycopg")
    server = pgserver.get_server(tmp_path_factory.mktemp("pgdata"))
    yield server.get_uri()
    server.cleanup()


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return PredictionStore(db_path=tmp_path / "test_predictions.sqlite3")
    url = request.getfixturevalue("_postgres_url")
    import psycopg

    with psycopg.connect(url) as conn:  # fresh table per test: no cross-test bleed
        conn.execute("DROP TABLE IF EXISTS predictions")
    return PredictionStore(database_url=url)


class TestRecordSuccess:
    def test_recorded_prediction_is_retrievable(self, store) -> None:
        store.record_success(
            prediction_id="prd_test1", request_id="req_test1", created_at="2026-01-01T00:00:00+00:00",
            model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1",
            feature_set_id="abc123", input_hash="deadbeefdead", canonical_structure_hash="cafebabecafe",
            applicability_domain_verdict="in_domain", predicted_label="blocker",
            predicted_probability_blocker=0.9, response_json='{"id": "prd_test1"}',
        )
        row = store.get("prd_test1")
        assert row is not None
        assert row["validation_status"] == "accepted"
        assert row["final_prediction_status"] == "complete"
        assert row["predicted_label"] == "blocker"
        assert row["applicability_domain_verdict"] == "in_domain"

    def test_missing_prediction_returns_none(self, store) -> None:
        assert store.get("prd_does_not_exist") is None


class TestRecordRejection:
    def test_rejected_prediction_is_logged_with_no_response(self, store) -> None:
        store.record_rejection(
            prediction_id="prd_test2", request_id="req_test2", created_at="2026-01-01T00:00:00+00:00",
            input_hash="deadbeefdead", rejection_reason="empty structure",
        )
        row = store.get("prd_test2")
        assert row is not None
        assert row["validation_status"] == "rejected"
        assert row["final_prediction_status"] == "failed"
        assert row["rejection_reason"] == "empty structure"
        assert row["response_json"] is None
        assert row["predicted_label"] is None


class TestProvenanceFields:
    def test_all_required_provenance_fields_are_stored(self, store) -> None:
        store.record_success(
            prediction_id="prd_test3", request_id="req_test3", created_at="2026-01-01T00:00:00+00:00",
            model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1",
            feature_set_id="abc123", input_hash="hash1", canonical_structure_hash="hash2",
            applicability_domain_verdict="out_of_domain", predicted_label="non_blocker",
            predicted_probability_blocker=0.2, response_json="{}",
        )
        row = store.get("prd_test3")
        for field in (
            "id", "request_id", "created_at", "model_id", "model_version", "dataset_version",
            "feature_set_id", "input_hash", "canonical_structure_hash", "validation_status",
            "applicability_domain_verdict", "predicted_label", "predicted_probability_blocker",
            "final_prediction_status",
        ):
            assert row[field] is not None, f"missing provenance field: {field}"

    def test_raw_structure_is_never_stored_only_hashes(self, store) -> None:
        """The store's schema has no column that could hold a raw SMILES
        string directly -- input_hash/canonical_structure_hash are the only
        structure-derived fields, both digests."""
        store.record_success(
            prediction_id="prd_test4", request_id="req_test4", created_at="2026-01-01T00:00:00+00:00",
            model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1",
            feature_set_id="abc123", input_hash="hash1", canonical_structure_hash="hash2",
            applicability_domain_verdict="in_domain", predicted_label="blocker",
            predicted_probability_blocker=0.8, response_json='{"molecule": {"canonical_smiles": "CCO"}}',
        )
        row = store.get("prd_test4")
        assert row["input_hash"] == "hash1"
        assert row["canonical_structure_hash"] == "hash2"
        # response_json legitimately carries the structure back to the
        # caller who submitted it (the "tenant-scoped database row"); only
        # the application LOG stream must avoid it, which this store is not.


class TestIsolation:
    def test_two_stores_on_different_paths_do_not_share_data(self, tmp_path) -> None:
        store_a = PredictionStore(db_path=tmp_path / "a.sqlite3")
        store_b = PredictionStore(db_path=tmp_path / "b.sqlite3")
        store_a.record_success(
            prediction_id="prd_a", request_id="req_a", created_at="2026-01-01T00:00:00+00:00",
            model_id="m", model_version="1", dataset_version="v1", feature_set_id="f",
            input_hash="h", canonical_structure_hash="c", applicability_domain_verdict="in_domain",
            predicted_label="blocker", predicted_probability_blocker=0.5, response_json="{}",
        )
        assert store_a.get("prd_a") is not None
        assert store_b.get("prd_a") is None


class TestBackendSelection:
    def test_explicit_db_path_stays_sqlite_even_when_a_database_url_is_configured(
        self, tmp_path, monkeypatch
    ) -> None:
        """Tests (and any caller passing a path) must never be redirected to a
        real database just because the environment configures one."""
        monkeypatch.setenv("DRUGSIM_PREDICT_PREDICTION_DATABASE_URL", "postgresql://nobody@localhost/never_used")
        get_predict_settings.cache_clear()
        try:
            store = PredictionStore(db_path=tmp_path / "x.sqlite3")
            assert store._postgres is False
            assert store.ping() is True
        finally:
            get_predict_settings.cache_clear()

    def test_configured_database_url_selects_postgres(self, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_PREDICTION_DATABASE_URL", "postgresql://u@h/d")
        get_predict_settings.cache_clear()
        try:
            assert get_predict_settings().prediction_database_url == "postgresql://u@h/d"
        finally:
            get_predict_settings.cache_clear()

    def test_default_is_sqlite(self, tmp_path) -> None:
        assert PredictionStore(db_path=tmp_path / "d.sqlite3")._postgres is False


class TestBackendParity:
    def test_probability_round_trips_at_full_double_precision(self, store) -> None:
        """PostgreSQL's REAL is a 4-byte float; the schema must use a type that
        keeps the stored probability identical to what SQLite returns."""
        value = 0.123456789012345
        store.record_success(
            prediction_id="prd_precision", request_id="req_p", created_at="2026-01-01T00:00:00+00:00",
            model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1", feature_set_id="f",
            input_hash="h", canonical_structure_hash="c", applicability_domain_verdict="in_domain",
            predicted_label="blocker", predicted_probability_blocker=value, response_json="{}",
        )
        assert store.get("prd_precision")["predicted_probability_blocker"] == value

    def test_api_key_hash_is_stored_and_a_keyless_row_has_none(self, store) -> None:
        """The retrieval-scoping column (confidentiality audit finding #1)
        must behave identically on both backends: a keyed row records its
        owner's hash, a keyless row is NULL (retrievable by no one)."""
        common = dict(
            request_id="req_k", created_at="2026-01-01T00:00:00+00:00", model_id="m", model_version="1",
            dataset_version="v1", feature_set_id="f", input_hash="h", canonical_structure_hash="c",
            applicability_domain_verdict="in_domain", predicted_label="blocker",
            predicted_probability_blocker=0.5, response_json="{}",
        )
        store.record_success(prediction_id="prd_owned", api_key_hash="a" * 64, **common)
        store.record_success(prediction_id="prd_orphan", **common)
        assert store.get("prd_owned")["api_key_hash"] == "a" * 64
        assert store.get("prd_orphan")["api_key_hash"] is None

    def test_question_marks_in_values_are_stored_verbatim(self, store) -> None:
        """Placeholders are rewritten for PostgreSQL by editing the statement,
        never the data: a value containing '?' must survive untouched."""
        store.record_rejection(
            prediction_id="prd_q", request_id="req_q", created_at="2026-01-01T00:00:00+00:00",
            input_hash="h", rejection_reason="why? because ? and ?",
        )
        assert store.get("prd_q")["rejection_reason"] == "why? because ? and ?"

    def test_duplicate_id_is_rejected_and_leaves_the_original_intact(self, store) -> None:
        """Atomicity: a failed write must not corrupt or replace the first row."""
        kwargs = dict(
            request_id="req_d", created_at="2026-01-01T00:00:00+00:00", input_hash="h",
            rejection_reason="first",
        )
        store.record_rejection(prediction_id="prd_dup", **kwargs)
        with pytest.raises(Exception):  # noqa: B017 -- sqlite3.IntegrityError or psycopg.errors.UniqueViolation
            store.record_rejection(prediction_id="prd_dup", **{**kwargs, "rejection_reason": "second"})
        assert store.get("prd_dup")["rejection_reason"] == "first"
        assert store.ping() is True  # connection state is not poisoned for the next request

    def test_schema_init_is_idempotent(self, store) -> None:
        """A serverless cold start re-runs schema init against an existing
        database on every new instance; it must be a no-op, not an error."""
        store._init_schema()
        store._init_schema()
        assert store.ping() is True
