"""Confidentiality audit (2026-08-22): a caller must not be able to
retrieve another caller's stored prediction -- including its canonical
chemical structure -- via ``GET /predict/{id}``.

Before this test existed, this codebase had no such guarantee at all:
``PredictionStore`` recorded no notion of who created a row, so any caller
holding any one configured API key could fetch any prediction ID. This
file pins the fix: retrieval is scoped to the API key that created the
row, and a mismatch is indistinguishable from "no such ID" (never a 403
that would confirm the ID exists for someone unauthorized to see it).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drugsim_predict.api import app, get_store
from drugsim_predict.store import PredictionStore

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact, pytest.mark.security]


@pytest.fixture
def client(tmp_path):
    test_store = PredictionStore(db_path=tmp_path / "ownership_test.sqlite3")
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _predict_body(smiles: str = "CCO") -> dict:
    return {"structure": {"format": "smiles", "value": smiles}}


class TestPredictionRetrievalIsolation:
    def test_creator_can_retrieve_their_own_prediction(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "alice-key,bob-key")
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()

        created = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice-key"}).json()
        r = client.get(f"/predict/{created['id']}", headers={"X-API-Key": "alice-key"})
        assert r.status_code == 200
        assert r.json() == created

    def test_a_different_configured_key_cannot_retrieve_it(self, client, monkeypatch) -> None:
        """The central regression: bob holds a genuinely valid API key, but
        not alice's -- he must not be able to read alice's molecule."""
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "alice-key,bob-key")
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()

        created = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice-key"}).json()
        r = client.get(f"/predict/{created['id']}", headers={"X-API-Key": "bob-key"})
        assert r.status_code == 404
        # Never leaks the structure, model output, or ANY field of the real record.
        body = r.json()
        assert "molecule" not in body
        assert "estimate" not in body

    def test_mismatch_and_genuinely_unknown_id_return_the_same_response(self, client, monkeypatch) -> None:
        """A wrong-owner 404 must be indistinguishable from a real 404 --
        otherwise the distinction itself discloses that the ID exists."""
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "alice-key,bob-key")
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()

        created = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice-key"}).json()
        wrong_owner = client.get(f"/predict/{created['id']}", headers={"X-API-Key": "bob-key"})
        unknown_id = client.get("/predict/prd_00000000000000000000000000", headers={"X-API-Key": "bob-key"})

        assert wrong_owner.status_code == unknown_id.status_code == 404
        assert wrong_owner.json()["type"] == unknown_id.json()["type"]
        assert wrong_owner.json()["title"] == unknown_id.json()["title"]

    def test_retrieval_without_any_key_is_rejected_before_reaching_ownership_logic(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "alice-key,bob-key")
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()

        created = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice-key"}).json()
        r = client.get(f"/predict/{created['id']}")
        assert r.status_code == 401

    def test_isolation_is_skipped_when_no_key_auth_is_configured(self, client) -> None:
        """Matches every other route's permissive-when-unconfigured
        behaviour (local/dev with no DRUGSIM_PREDICT_API_KEYS set) --
        there is no caller identity to scope by in that mode at all."""
        from drugsim_predict.settings import get_predict_settings

        assert get_predict_settings().api_key_set == frozenset()
        created = client.post("/predict", json=_predict_body()).json()
        r = client.get(f"/predict/{created['id']}")
        assert r.status_code == 200
        assert r.json() == created

    def test_a_row_written_before_this_migration_is_retrievable_by_no_one(self, client, monkeypatch) -> None:
        """A pre-existing row with api_key_hash IS NULL (written under an
        older schema, or while no key was configured) must fail closed
        once key auth is active -- never fall open to "anyone can read
        legacy rows."""
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "alice-key")
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()

        store = app.dependency_overrides[get_store]()
        store.record_success(
            prediction_id="prd_legacyrow00000000000000000",
            request_id="req_legacy",
            created_at="2026-01-01T00:00:00+00:00",
            model_id="herg_inhibition",
            model_version="0.1.0",
            dataset_version="v1",
            feature_set_id="legacy",
            input_hash="deadbeef",
            canonical_structure_hash="deadbeef",
            applicability_domain_verdict="in_domain",
            predicted_label="non_blocker",
            predicted_probability_blocker=0.1,
            response_json='{"id": "prd_legacyrow00000000000000000"}',
            # api_key_hash intentionally omitted -- simulates a pre-migration row.
        )
        r = client.get("/predict/prd_legacyrow00000000000000000", headers={"X-API-Key": "alice-key"})
        assert r.status_code == 404
