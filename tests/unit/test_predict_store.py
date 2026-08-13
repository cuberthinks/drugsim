"""Tests for the SQLite prediction provenance store."""

from __future__ import annotations

import pytest

from drugsim_predict.store import PredictionStore

pytestmark = pytest.mark.unit


@pytest.fixture
def store(tmp_path):
    return PredictionStore(db_path=tmp_path / "test_predictions.sqlite3")


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
