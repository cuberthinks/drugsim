"""Confidentiality audit (2026-08-22), item 3 (error safety): an HTTP
error response is a different disclosure surface than a log line, and
tests/security/test_no_structure_in_logs.py only covers the latter.

``drugsim_core.errors.StructureError`` is designed so its ``message`` is
always a fixed template ("could not parse smiles structure") and the real
diagnostic -- which the code's own comments note can embed RDKit's raw
parser output, and therefore potentially fragments of the submitted
structure -- lives only in ``context["detail"]``, deliberately never read
by the API layer. This file proves that design holds end-to-end: a
malformed structure built from a recognizable, "confidential-looking"
payload must not have that payload echoed back anywhere in the HTTP
response body, even though the response necessarily explains what kind of
problem occurred.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drugsim_predict.api import app, get_store
from drugsim_predict.store import PredictionStore

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact, pytest.mark.security]

#: Deliberately not a real molecule -- garbled so RDKit's SMILES parser
#: fails (rather than merely rejecting an unlikely-but-valid structure),
#: which is the path most likely to make RDKit print the raw input to
#: stderr (captured as StructureError's context["detail"]). The marker
#: text stands in for a proprietary fragment a real user might paste.
_MALFORMED_CONFIDENTIAL_LOOKING_SMILES = "C1(PROPRIETARY-COMPOUND-7f3a9c)[C@@H](((("


@pytest.fixture
def client(tmp_path):
    test_store = PredictionStore(db_path=tmp_path / "error_response_test.sqlite3")
    app.dependency_overrides[get_store] = lambda: test_store
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestErrorResponsesNeverLeakStructures:
    def test_malformed_structure_error_response_does_not_echo_the_input(self, client) -> None:
        r = client.post(
            "/predict",
            json={"structure": {"format": "smiles", "value": _MALFORMED_CONFIDENTIAL_LOOKING_SMILES}},
        )
        assert r.status_code == 422
        raw_body = r.text
        assert _MALFORMED_CONFIDENTIAL_LOOKING_SMILES not in raw_body
        assert "PROPRIETARY-COMPOUND-7f3a9c" not in raw_body

    def test_response_still_explains_the_problem_class(self, client) -> None:
        """Safety must not come at the cost of a useless error -- the
        response should still say a structure problem occurred, just not
        echo the structure itself."""
        r = client.post(
            "/predict",
            json={"structure": {"format": "smiles", "value": _MALFORMED_CONFIDENTIAL_LOOKING_SMILES}},
        )
        body = r.json()
        assert body["type"] == "https://drugsim.internal/errors/invalid-structure"
        assert "structure" in body["detail"].lower() or "parse" in body["detail"].lower()

    def test_validation_rejection_at_the_schema_layer_does_not_echo_the_input(self, client) -> None:
        """A different code path (FastAPI's own request-validation
        exception handler, not StructureError) -- covers the case where a
        structure is rejected before ever reaching the chemistry pipeline
        (e.g. too long)."""
        too_long = "C" * 6001  # over StructureInput's max_length=6000
        r = client.post("/predict", json={"structure": {"format": "smiles", "value": too_long}})
        assert r.status_code == 422
        assert too_long not in r.text

    def test_unexpected_error_path_does_not_echo_the_input(self, client) -> None:
        """The generic ``except Exception`` catch-all in POST /predict logs
        only the exception type (see api.py's own comment on that handler)
        -- confirm the HTTP response matches that same discipline, using a
        forced failure so the test does not depend on finding a real input
        that happens to trigger an unhandled exception."""
        import drugsim_predict.api as api_module

        original_run_inference = api_module.run_inference
        secret_marker = "UNHANDLED-FAILURE-MARKER-b91e"

        def boom(*_args: object, **_kwargs: object) -> None:
            raise KeyError(f"simulated failure while handling {secret_marker}")

        api_module.run_inference = boom  # type: ignore[assignment]
        try:
            r = client.post("/predict", json={"structure": {"format": "smiles", "value": "CCO"}})
        finally:
            api_module.run_inference = original_run_inference

        assert r.status_code == 500
        assert secret_marker not in r.text
