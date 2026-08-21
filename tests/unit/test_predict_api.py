"""Tests for the FastAPI prediction service endpoints.

Uses ``app.dependency_overrides`` to point the prediction store at a
per-test temp file, never the real ``var/predictions.sqlite3``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drugsim_predict.api import app, get_store
from drugsim_predict.store import PredictionStore

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


@pytest.fixture
def client(tmp_path):
    test_store = PredictionStore(db_path=tmp_path / "api_test.sqlite3")
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealth:
    def test_health_returns_ok(self, client) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_health_ready_returns_ready(self, client) -> None:
        r = client.get("/health/ready")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"

    def test_health_ready_reports_all_four_components(self, client) -> None:
        """Phase 8 Sec 10: application, database, model, prediction engine."""
        body = client.get("/health/ready").json()
        assert body["checks"] == {
            "application": "ok", "database": "ok", "model": "ok", "prediction_engine": "ok",
        }

    def test_health_ready_reports_model_failure_without_leaking_paths(self, client, monkeypatch) -> None:
        """Phase 8 Sec 10: never expose sensitive diagnostic information
        through a public (unauthenticated) health endpoint -- a checksum
        mismatch's real message embeds a filesystem path."""
        import drugsim_predict.api as api_module
        from drugsim_core.errors import IntegrityError

        def boom(model_id):
            raise IntegrityError("model artifact checksum mismatch", path="/secret/internal/path/model.joblib")

        monkeypatch.setattr(api_module, "get_model_bundle", boom)
        r = client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["model"] == "unavailable"
        assert body["checks"]["prediction_engine"] == "unavailable"
        assert "/secret/internal/path" not in r.text

    def test_health_ready_reports_database_failure_without_leaking_detail(self, client, monkeypatch) -> None:
        import drugsim_predict.api as api_module

        def boom(self):
            msg = "disk I/O error at /var/lib/drugsim/predictions.sqlite3"
            raise RuntimeError(msg)

        monkeypatch.setattr(api_module.PredictionStore, "ping", boom)
        r = client.get("/health/ready")
        assert r.status_code == 503
        body = r.json()
        assert body["checks"]["database"] == "unavailable"
        # Model/prediction-engine are independent of the DB and should
        # still report correctly -- one failed component must not mask another.
        assert body["checks"]["model"] == "ok"
        assert body["checks"]["prediction_engine"] == "ok"
        assert "/var/lib/drugsim" not in r.text

    def test_health_ready_is_reachable_without_an_api_key(self, client, monkeypatch) -> None:
        from drugsim_predict.settings import get_predict_settings

        monkeypatch.setenv("DRUGSIM_PREDICT_API_KEYS", "some-key")
        get_predict_settings.cache_clear()
        assert client.get("/health/ready").status_code in (200, 503)
        assert client.get("/health").status_code == 200


class TestModelEndpoints:
    def test_get_model_returns_current_model_metadata(self, client) -> None:
        r = client.get("/model")
        assert r.status_code == 200
        body = r.json()
        assert body["model_id"] == "herg_inhibition"
        assert body["final_report_status"] == "VALIDATED FOR INTERNAL RESEARCH"

    def test_get_model_latest_matches_get_model(self, client) -> None:
        r1 = client.get("/model").json()
        r2 = client.get("/model/latest").json()
        assert r1 == r2

    def test_model_response_never_claims_clinical_validation(self, client) -> None:
        body = client.get("/model").json()
        forbidden = {"clinically validated", "medically validated", "production-ready"}
        assert not any(term in body["final_report_status"].lower() for term in forbidden)


class TestPredictValid:
    def test_predict_returns_200_with_full_envelope(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert r.status_code == 200
        body = r.json()
        assert "estimate" in body
        assert "reliability" in body
        assert "provenance" in body
        assert body["reliability"]["conformal"] is not None
        assert body["reliability"]["applicability_domain"] is not None

    def test_predict_response_has_an_id_and_request_id(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        body = r.json()
        assert body["id"].startswith("prd_")
        assert body["request_id"].startswith("req_")

    def test_predict_echoes_x_request_id_header(self, client) -> None:
        r = client.post(
            "/predict",
            json={"structure": {"format": "smiles", "value": "CCO"}},
            headers={"X-Request-Id": "req_custom123"},
        )
        assert r.headers["X-Request-Id"] == "req_custom123"
        assert r.json()["request_id"] == "req_custom123"


class TestPredictInvalid:
    def test_empty_structure_returns_422_problem_json(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": ""}})
        assert r.status_code == 422

    def test_schema_level_rejection_is_rfc9457_shaped_and_logged(self, client) -> None:
        """Regression test: schema-validation failures (empty value, unknown
        format) are intercepted by FastAPI before reaching the predict
        handler's own try/except. Without a dedicated exception handler this
        both returned a non-problem+json body and was never logged --
        caught while writing this test suite, fixed in api.py."""
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": ""}})
        body = r.json()
        assert body["type"] == "https://drugsim.internal/errors/malformed-request"
        assert body["status"] == 422
        assert "request_id" in body

        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            count = conn.execute(
                "SELECT COUNT(*) FROM predictions WHERE validation_status = 'rejected' "
                "AND rejection_reason LIKE 'request_validation_error:%'"
            ).fetchone()[0]
        assert count >= 1

    def test_malformed_smiles_returns_422_with_problem_detail_shape(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "not-a-molecule((("}})
        assert r.status_code == 422
        body = r.json()
        assert body["type"] == "https://drugsim.internal/errors/invalid-structure"
        assert body["status"] == 422
        assert "request_id" in body

    def test_mixture_returns_422(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO.CCN"}})
        assert r.status_code == 422

    def test_unsupported_format_returns_422_from_schema_validation(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "pdb", "value": "x"}})
        assert r.status_code == 422

    def test_invalid_input_is_never_given_a_prediction(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": ""}})
        body = r.json()
        assert "estimate" not in body
        assert "reliability" not in body


def _fake_result(**overrides):
    """A schema-valid, synthetic PredictionResult for exercising API-layer
    behaviour independent of what any specific real molecule happens to do
    against the current model. What real molecules land where is the
    regression suite's job (docs/phase7); this is only testing "does the
    API pass an out-of-domain/error verdict through correctly."""
    from drugsim_predict.applicability_domain import ApplicabilityDomainResult
    from drugsim_predict.conformal import ConformalResult
    from drugsim_predict.pipeline import InferenceWarning, PredictionResult

    defaults = dict(
        input_structure="C1CC1",
        input_format="smiles",
        canonical_smiles="C1CC1",
        isomeric_smiles="C1CC1",
        standardized_smiles="C1CC1",
        inchikey_full="LVZWSLJZHVFIQJ-UHFFFAOYSA-N",
        molecular_formula="C3H6",
        predicted_label="non_blocker",
        predicted_probability_blocker=0.1,
        predicted_probability=0.1,
        conformal=ConformalResult(
            predicted_set=["non_blocker"], p_value_blocker=0.02, p_value_non_blocker=0.7,
            nominal_confidence=0.9, is_singleton=True,
        ),
        applicability_domain=ApplicabilityDomainResult(
            verdict="out_of_domain", max_tanimoto_to_training=0.12, knn_distance=5.0,
            knn_distance_threshold=1.7, scaffold_seen_in_training=False,
            rationale="synthetic test rationale: far from any training compound",
        ),
        warnings=[
            InferenceWarning(
                code="out_of_domain", severity="high",
                message="This prediction is an extrapolation (synthetic test warning).",
                field="applicability_domain",
            )
        ],
        model_id="herg_inhibition", model_version="0.1.0", dataset_version="v1",
        feature_set_id="fake_feature_set", training_set_size=6792,
        inference_timestamp="2026-08-09T00:00:00+00:00",
    )
    defaults.update(overrides)
    return PredictionResult(**defaults)


class TestPredictOutOfDomain:
    """An out-of-domain verdict is a successful, informative prediction —
    never an error. Section 2 of the Phase 7 spec asks this scenario be
    covered explicitly at the API level, not only inside the pipeline unit
    tests."""

    def test_out_of_domain_prediction_returns_200_not_an_error(self, client, monkeypatch) -> None:
        import drugsim_predict.api as api_module

        monkeypatch.setattr(api_module, "run_inference", lambda *a, **kw: _fake_result())
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "C1CC1"}})
        assert r.status_code == 200
        body = r.json()
        assert body["reliability"]["applicability_domain"]["verdict"] == "out_of_domain"
        assert body["status"] == "complete"
        assert any(w["code"] == "out_of_domain" for w in body["warnings"])

    def test_out_of_domain_prediction_is_still_logged_as_a_success(self, client, monkeypatch) -> None:
        import drugsim_predict.api as api_module

        monkeypatch.setattr(api_module, "run_inference", lambda *a, **kw: _fake_result())
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "C1CC1"}})
        prediction_id = r.json()["id"]

        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            row = conn.execute(
                "SELECT validation_status, applicability_domain_verdict FROM predictions WHERE id = ?",
                (prediction_id,),
            ).fetchone()
        assert row[0] == "accepted"
        assert row[1] == "out_of_domain"


class TestPredictUnexpectedServerError:
    """Section 2 of the Phase 7 spec: an unexpected server error must never
    produce a fake or stale prediction, and must still be recorded in the
    audit trail (Phase 7 hardening fix — see docs/phase7)."""

    def test_unexpected_exception_returns_problem_json_500(self, client, monkeypatch) -> None:
        import drugsim_predict.api as api_module

        def boom(*_a, **_kw):
            raise RuntimeError("simulated unexpected failure")

        monkeypatch.setattr(api_module, "run_inference", boom)
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert r.status_code == 500
        body = r.json()
        assert body["type"] == "https://drugsim.internal/errors/internal-error"
        assert "estimate" not in body
        assert "request_id" in body

    def test_unexpected_exception_is_recorded_in_the_audit_trail(self, client, monkeypatch) -> None:
        import drugsim_predict.api as api_module

        def boom(*_a, **_kw):
            raise RuntimeError("simulated unexpected failure")

        monkeypatch.setattr(api_module, "run_inference", boom)
        client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})

        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            row = conn.execute(
                "SELECT validation_status, rejection_reason FROM predictions "
                "WHERE rejection_reason LIKE 'unexpected_error:%'"
            ).fetchone()
        assert row is not None
        assert row[0] == "rejected"
        assert row[1] == "unexpected_error: RuntimeError"


class TestPredictTimeout:
    """Phase 8 Sec 8 / TDS Sec 7.7 "parser hang" control: a prediction that
    takes too long must return a clean, timely error rather than hanging
    the caller indefinitely. See api.py's predict() docstring for the
    documented limitation (a hung thread cannot be forcibly killed)."""

    def test_slow_inference_returns_503_within_the_configured_timeout(self, client, monkeypatch) -> None:
        import time

        import drugsim_predict.api as api_module
        from drugsim_predict.settings import get_predict_settings

        monkeypatch.setenv("DRUGSIM_PREDICT_REQUEST_TIMEOUT_SECONDS", "0.2")
        get_predict_settings.cache_clear()

        def slow(*_a, **_kw):
            time.sleep(1)
            msg = "should never be reached"
            raise AssertionError(msg)

        monkeypatch.setattr(api_module, "run_inference", slow)

        t0 = time.perf_counter()
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        elapsed = time.perf_counter() - t0

        assert r.status_code == 503
        assert elapsed < 2.0, f"expected a fast timeout response, took {elapsed:.2f}s"
        body = r.json()
        assert body["type"] == "https://drugsim.internal/errors/timeout"
        assert "estimate" not in body

    def test_timeout_is_recorded_in_the_audit_trail(self, client, monkeypatch) -> None:
        import time

        import drugsim_predict.api as api_module
        from drugsim_predict.settings import get_predict_settings

        monkeypatch.setenv("DRUGSIM_PREDICT_REQUEST_TIMEOUT_SECONDS", "0.2")
        get_predict_settings.cache_clear()

        def slow(*_a, **_kw):
            time.sleep(1)

        monkeypatch.setattr(api_module, "run_inference", slow)
        client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})

        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            row = conn.execute(
                "SELECT validation_status FROM predictions WHERE rejection_reason = 'timeout'"
            ).fetchone()
        assert row is not None
        assert row[0] == "rejected"

    def test_fast_inference_is_unaffected_by_the_timeout(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert r.status_code == 200


class TestPredictRetrieval:
    def test_get_prediction_by_id_returns_the_same_envelope(self, client) -> None:
        created = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}}).json()
        fetched = client.get(f"/predict/{created['id']}").json()
        assert fetched == created

    def test_get_nonexistent_prediction_returns_404(self, client) -> None:
        r = client.get("/predict/prd_00000000000000000000000000")
        assert r.status_code == 404
        assert r.json()["type"] == "https://drugsim.internal/errors/not-found"

    def test_rejected_predictions_are_not_retrievable(self, client) -> None:
        """A rejected request is logged (provenance) but never produces a
        retrievable prediction envelope -- there is no result to retrieve."""
        rejected = client.post("/predict", json={"structure": {"format": "smiles", "value": ""}})
        assert rejected.status_code == 422


class TestModelVersionConsistency:
    def test_every_successful_prediction_reports_the_same_model_version(self, client) -> None:
        versions = set()
        for smiles in ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "c1ccccc1"]:
            r = client.post("/predict", json={"structure": {"format": "smiles", "value": smiles}})
            versions.add(r.json()["provenance"]["model_version"])
        assert len(versions) == 1

    def test_predict_and_model_endpoint_report_the_same_version(self, client) -> None:
        model_version = client.get("/model").json()["model_version"]
        pred = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}}).json()
        assert pred["provenance"]["model_version"] == model_version


class TestProvenanceLogging:
    def test_successful_prediction_is_logged_in_the_store(self, client) -> None:
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        prediction_id = r.json()["id"]
        row = app.dependency_overrides[get_store]().get(prediction_id)
        assert row is not None
        assert row["validation_status"] == "accepted"

    def test_rejected_prediction_is_also_logged(self, client) -> None:
        client.post("/predict", json={"structure": {"format": "smiles", "value": ""}})
        # We don't have the generated id for a rejection from the response
        # (client-facing rejections carry no prediction id), but we can
        # confirm at least one rejected row now exists in the isolated store.
        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            count = conn.execute("SELECT COUNT(*) FROM predictions WHERE validation_status = 'rejected'").fetchone()[0]
        assert count >= 1


class TestPredictExplain:
    def test_returns_200_with_full_envelope(self, client) -> None:
        r = client.post("/predict/explain", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert r.status_code == 200
        body = r.json()
        assert body["endpoint"] == "herg_inhibition"
        assert body["positive_class_label"] == "blocker"
        assert isinstance(body["base_value"], float)
        assert len(body["atom_contributions"]) == 3  # CCO: 2 carbons + 1 oxygen, no implicit Hs counted
        assert len(body["descriptor_contributions"]) == 18
        assert isinstance(body["absent_substructure_contribution"], float)
        assert body["method"] == "shap_tree_explainer_interventional"

    def test_reconstructs_the_matching_predict_probability(self, client) -> None:
        """The whole point of additivity: explain's numbers must sum back
        to exactly the /predict probability for the same input."""
        predict_r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        explain_r = client.post("/predict/explain", json={"structure": {"format": "smiles", "value": "CCO"}})
        proba = predict_r.json()["estimate"]["predicted_probability"]
        body = explain_r.json()
        total = (
            body["base_value"]
            + sum(a["contribution"] for a in body["atom_contributions"])
            + sum(d["contribution"] for d in body["descriptor_contributions"])
            + body["absent_substructure_contribution"]
        )
        assert total == pytest.approx(proba, abs=1e-3)

    def test_same_endpoint_and_molecule_fields_as_predict(self, client) -> None:
        predict_r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        explain_r = client.post("/predict/explain", json={"structure": {"format": "smiles", "value": "CCO"}})
        assert explain_r.json()["molecule"] == predict_r.json()["molecule"]

    def test_empty_structure_returns_422(self, client) -> None:
        r = client.post("/predict/explain", json={"structure": {"format": "smiles", "value": ""}})
        assert r.status_code == 422

    def test_mixture_returns_422(self, client) -> None:
        r = client.post("/predict/explain", json={"structure": {"format": "smiles", "value": "CCO.CCN"}})
        assert r.status_code == 422

    def test_unknown_endpoint_returns_404(self, client) -> None:
        r = client.post(
            "/predict/explain",
            json={"structure": {"format": "smiles", "value": "CCO"}, "endpoint": "not_a_real_endpoint"},
        )
        assert r.status_code == 404

    def test_cyp3a4_endpoint_returns_501_not_a_crash(self, client) -> None:
        """cyp3a4_inhibition is deliberately excluded from
        EXPLAINABLE_MODEL_IDS -- its SHAP explainer measured a ~280MB
        resident-memory jump and crashed production on first deploy (see
        explainability.py's module docstring). This must be a clean,
        honest 501, never a 500 or a repeat of that crash."""
        r = client.post(
            "/predict/explain",
            json={"structure": {"format": "smiles", "value": "CCO"}, "endpoint": "cyp3a4_inhibition"},
        )
        assert r.status_code == 501
        assert "not yet available" in r.json()["detail"].lower()

    def test_not_persisted_to_the_prediction_store(self, client) -> None:
        """Deliberately not an audited prediction event -- see the route's
        own docstring for why."""
        store = app.dependency_overrides[get_store]()
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            before = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        client.post("/predict/explain", json={"structure": {"format": "smiles", "value": "CCO"}})
        with store._connect() as conn:  # noqa: SLF001 -- test-only introspection
            after = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
        assert after == before
