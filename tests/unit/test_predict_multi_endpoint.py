"""Phase 9 Sec 19: tests for the multi-endpoint prediction-engine refactor.

Covers exactly what the phase spec asks for on the serving side: model
loading/checksum for a SECOND endpoint, inference producing that endpoint's
own label vocabulary, the promotion gate refusing to serve an unvalidated
endpoint, the API's endpoint-discovery route, and -- most importantly --
that none of this changed hERG's existing behaviour or contract.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from fastapi.testclient import TestClient

from drugsim_core.errors import EndpointNotAvailableError, UnknownEndpointError
from drugsim_predict.conformal import compute_conformal_set
from drugsim_predict.model_registry import get_model_bundle, list_registered_endpoints, load_model_bundle
from drugsim_predict.pipeline import run_inference

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


@pytest.fixture(scope="module")
def herg_bundle():
    return load_model_bundle(model_id="herg_inhibition")


@pytest.fixture(scope="module")
def cyp3a4_bundle():
    return load_model_bundle(model_id="cyp3a4_inhibition")


class TestModelRegistryMultiEndpoint:
    def test_resolves_cyp3a4_by_model_id(self, cyp3a4_bundle) -> None:
        assert cyp3a4_bundle.model_id == "cyp3a4_inhibition"
        assert cyp3a4_bundle.final_report_status == "VALIDATED FOR INTERNAL RESEARCH"

    def test_herg_default_is_unchanged_by_the_refactor(self, herg_bundle) -> None:
        """get_model_bundle()/load_model_bundle() with no model_id must keep
        returning exactly the hERG bundle they always did."""
        assert herg_bundle.model_id == "herg_inhibition"
        default = load_model_bundle()
        assert default.model_id == "herg_inhibition"
        assert default.model_checksum == herg_bundle.model_checksum

    def test_cyp3a4_and_herg_have_independent_checksums_and_training_sizes(self, herg_bundle, cyp3a4_bundle) -> None:
        assert cyp3a4_bundle.model_checksum != herg_bundle.model_checksum
        assert cyp3a4_bundle.training_set_size != herg_bundle.training_set_size

    def test_cyp3a4_has_its_own_label_vocabulary(self, cyp3a4_bundle, herg_bundle) -> None:
        assert cyp3a4_bundle.positive_class_label == "inhibitor"
        assert cyp3a4_bundle.negative_class_label == "non_inhibitor"
        assert herg_bundle.positive_class_label == "blocker"
        assert herg_bundle.negative_class_label == "non_blocker"

    def test_unknown_model_id_raises_unknown_endpoint_error(self) -> None:
        with pytest.raises(UnknownEndpointError):
            load_model_bundle(model_id="not_a_real_endpoint")

    def test_get_model_bundle_caches_per_model_id(self) -> None:
        a = get_model_bundle("cyp3a4_inhibition")
        b = get_model_bundle("cyp3a4_inhibition")
        assert a is b
        assert get_model_bundle("herg_inhibition") is not a

    def test_list_registered_endpoints_includes_both(self) -> None:
        summaries = {s.model_id: s for s in list_registered_endpoints()}
        assert "herg_inhibition" in summaries
        assert "cyp3a4_inhibition" in summaries
        assert summaries["cyp3a4_inhibition"].final_report_status == "VALIDATED FOR INTERNAL RESEARCH"
        assert summaries["cyp3a4_inhibition"].training_set_size == 5344


class TestPipelineMultiEndpoint:
    def test_run_inference_routes_to_cyp3a4_by_model_id(self, cyp3a4_bundle) -> None:
        result = run_inference("CCO", model_id="cyp3a4_inhibition", bundle=cyp3a4_bundle)
        assert result.model_id == "cyp3a4_inhibition"
        assert result.predicted_label in ("inhibitor", "non_inhibitor")
        assert 0.0 <= result.predicted_probability <= 1.0

    def test_run_inference_default_still_produces_herg_vocabulary(self, herg_bundle) -> None:
        result = run_inference("CCO", bundle=herg_bundle)
        assert result.model_id == "herg_inhibition"
        assert result.predicted_label in ("blocker", "non_blocker")

    def test_promotion_gate_refuses_an_unvalidated_endpoint(self, cyp3a4_bundle) -> None:
        """An EXPERIMENTAL/REJECTED endpoint must never serve a normal
        prediction (Phase 9 Sec 14), enforced in the pipeline itself so
        every caller (API, health check, a future script) gets the same
        guarantee for free."""
        unvalidated = dataclasses.replace(cyp3a4_bundle, final_report_status="EXPERIMENTAL")
        with pytest.raises(EndpointNotAvailableError) as exc_info:
            run_inference("CCO", bundle=unvalidated)
        assert exc_info.value.model_id == "cyp3a4_inhibition"
        assert exc_info.value.final_report_status == "EXPERIMENTAL"

    def test_conformal_set_uses_the_endpoint_own_label_vocabulary(self, cyp3a4_bundle) -> None:
        result = compute_conformal_set(np.array([0.02, 0.98]), cyp3a4_bundle)
        assert result.predicted_set == ("inhibitor",)


class TestApiMultiEndpoint:
    @pytest.fixture()
    def client(self, monkeypatch) -> TestClient:
        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "")
        from drugsim_predict.api import app
        from drugsim_predict.settings import get_predict_settings

        get_predict_settings.cache_clear()
        return TestClient(app)

    def test_get_endpoints_lists_both_as_servable(self, client) -> None:
        response = client.get("/endpoints")
        assert response.status_code == 200
        by_id = {e["model_id"]: e for e in response.json()["endpoints"]}
        assert by_id["herg_inhibition"]["servable"] is True
        assert by_id["cyp3a4_inhibition"]["servable"] is True

    def test_predict_defaults_to_herg_and_keeps_its_exact_contract(self, client) -> None:
        """The existing hERG API contract must keep working unchanged:
        predicted_label from {blocker, non_blocker}, predicted_probability_blocker
        populated, endpoint field says herg_inhibition."""
        response = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert response.status_code == 200
        body = response.json()
        assert body["estimate"]["endpoint"] == "herg_inhibition"
        assert body["estimate"]["predicted_label"] in ("blocker", "non_blocker")
        assert isinstance(body["estimate"]["predicted_probability_blocker"], float)
        assert isinstance(body["estimate"]["predicted_probability"], float)

    def test_predict_with_cyp3a4_endpoint(self, client) -> None:
        response = client.post(
            "/predict",
            json={"structure": {"format": "smiles", "value": "CCO"}, "endpoint": "cyp3a4_inhibition"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["estimate"]["endpoint"] == "cyp3a4_inhibition"
        assert body["estimate"]["predicted_label"] in ("inhibitor", "non_inhibitor")
        # Legacy hERG-only field must be null for a non-hERG endpoint, never
        # a misleadingly-named "probability of blocker" for a different endpoint.
        assert body["estimate"]["predicted_probability_blocker"] is None
        assert body["provenance"]["model_id"] == "cyp3a4_inhibition"

    def test_predict_with_unknown_endpoint_returns_404(self, client) -> None:
        response = client.post(
            "/predict",
            json={"structure": {"format": "smiles", "value": "CCO"}, "endpoint": "not_a_real_endpoint"},
        )
        assert response.status_code == 404
        assert response.json()["type"].endswith("unknown-endpoint")

    def test_model_endpoint_accepts_endpoint_query_param(self, client) -> None:
        response = client.get("/model", params={"endpoint": "cyp3a4_inhibition"})
        assert response.status_code == 200
        assert response.json()["model_id"] == "cyp3a4_inhibition"
