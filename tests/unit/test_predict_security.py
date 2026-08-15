"""Tests for the Phase 8 access-control and abuse-protection middleware.

Uses ``app.dependency_overrides`` for the store (matching test_predict_api.py)
and ``monkeypatch.setenv`` + ``get_predict_settings.cache_clear()`` for
settings, since these middlewares read settings fresh on every request
rather than at construction time.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drugsim_predict.api import app, get_store
from drugsim_predict.security import reset_rate_limit_state
from drugsim_predict.settings import get_predict_settings
from drugsim_predict.store import PredictionStore

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


@pytest.fixture
def client(tmp_path):
    test_store = PredictionStore(db_path=tmp_path / "security_test.sqlite3")
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _predict_body(smiles: str = "CCO") -> dict:
    return {"structure": {"format": "smiles", "value": smiles}}


class TestApiKeyGate:
    def test_health_is_public_even_when_keys_are_configured(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "k1")
        get_predict_settings.cache_clear()
        assert client.get("/health").status_code == 200
        assert client.get("/health/ready").status_code == 200

    def test_predict_is_open_when_no_keys_are_configured(self, client) -> None:
        assert get_predict_settings().api_key_set == frozenset()
        r = client.post("/predict", json=_predict_body())
        assert r.status_code == 200

    def test_predict_rejects_missing_key_when_configured(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "k1,k2")
        get_predict_settings.cache_clear()
        r = client.post("/predict", json=_predict_body())
        assert r.status_code == 401
        assert r.headers["content-type"] == "application/problem+json"

    def test_predict_rejects_wrong_key(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "k1,k2")
        get_predict_settings.cache_clear()
        r = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "not-a-real-key"})
        assert r.status_code == 401

    def test_predict_accepts_any_configured_key(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "k1,k2")
        get_predict_settings.cache_clear()
        r = client.post("/predict", json=_predict_body(), headers={"X-API-Key": "k2"})
        assert r.status_code == 200

    def test_model_endpoint_is_also_gated(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "k1")
        get_predict_settings.cache_clear()
        assert client.get("/model").status_code == 401
        assert client.get("/model", headers={"X-API-Key": "k1"}).status_code == 200


class TestRateLimit:
    def test_requests_within_limit_succeed(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "5")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        for _ in range(5):
            assert client.post("/predict", json=_predict_body()).status_code == 200

    def test_requests_over_limit_are_rejected_with_429(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "2")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        assert client.post("/predict", json=_predict_body()).status_code == 200
        assert client.post("/predict", json=_predict_body()).status_code == 200
        r = client.post("/predict", json=_predict_body())
        assert r.status_code == 429
        assert r.headers["retry-after"] == "60"
        assert r.headers["content-type"] == "application/problem+json"

    def test_health_is_never_rate_limited(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "1")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        for _ in range(10):
            assert client.get("/health").status_code == 200

    def test_different_api_keys_have_independent_limits(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "1")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        assert client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice"}).status_code == 200
        # alice is now over her limit, bob is unaffected.
        assert client.post("/predict", json=_predict_body(), headers={"X-API-Key": "alice"}).status_code == 429
        assert client.post("/predict", json=_predict_body(), headers={"X-API-Key": "bob"}).status_code == 200

    def test_one_shared_api_key_does_not_pool_every_client_into_one_bucket(
        self, client, monkeypatch
    ) -> None:
        """Two people using the deployed app must not rate-limit each other.

        The browser bundle ships a single shared API key (see
        frontend/src/api/client.ts), so keying the limiter on the key alone
        put every visitor into one bucket -- the second colleague to click
        Predict got a 429 caused entirely by the first one's traffic. The
        bucket is keyed on the originating address too, which behind a
        reverse proxy means X-Forwarded-For rather than the proxy's own
        address.
        """
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "1")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        shared = {"X-API-Key": "shared-browser-key"}

        first = {**shared, "X-Forwarded-For": "203.0.113.10"}
        assert client.post("/predict", json=_predict_body(), headers=first).status_code == 200
        assert client.post("/predict", json=_predict_body(), headers=first).status_code == 429

        # A different visitor, same shared key: unaffected by the first one.
        second = {**shared, "X-Forwarded-For": "203.0.113.11"}
        assert client.post("/predict", json=_predict_body(), headers=second).status_code == 200

    def test_forwarded_for_chain_uses_the_originating_client(self, client, monkeypatch) -> None:
        """X-Forwarded-For accumulates proxies left-to-right; the client is first."""
        monkeypatch.setenv("DRUGSIM_PREDICT_RATE_LIMIT_REQUESTS_PER_MINUTE", "1")
        get_predict_settings.cache_clear()
        reset_rate_limit_state()
        shared = {"X-API-Key": "shared-browser-key"}

        # Same originating client, different intermediate proxy -- still one bucket.
        assert client.post(
            "/predict", json=_predict_body(),
            headers={**shared, "X-Forwarded-For": "203.0.113.10, 70.0.0.1"},
        ).status_code == 200
        assert client.post(
            "/predict", json=_predict_body(),
            headers={**shared, "X-Forwarded-For": "203.0.113.10, 70.0.0.2"},
        ).status_code == 429


class TestBodySizeLimit:
    def test_body_within_limit_is_accepted(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_MAX_REQUEST_BODY_BYTES", "65536")
        get_predict_settings.cache_clear()
        assert client.post("/predict", json=_predict_body()).status_code == 200

    def test_oversized_body_is_rejected_with_413(self, client, monkeypatch) -> None:
        monkeypatch.setenv("DRUGSIM_PREDICT_MAX_REQUEST_BODY_BYTES", "100")
        get_predict_settings.cache_clear()
        r = client.post("/predict", json=_predict_body("C" * 500))
        assert r.status_code == 413
        assert r.headers["content-type"] == "application/problem+json"

    def test_oversized_body_never_reaches_the_inference_pipeline(self, client, monkeypatch) -> None:
        """The 413 must come from the middleware, before any chemistry runs
        -- never a fabricated/partial prediction for a rejected request."""
        monkeypatch.setenv("DRUGSIM_PREDICT_MAX_REQUEST_BODY_BYTES", "100")
        get_predict_settings.cache_clear()
        r = client.post("/predict", json=_predict_body("C" * 500))
        body = r.json()
        assert "estimate" not in body
        assert "reliability" not in body
