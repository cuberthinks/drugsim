"""Tests for POST /v1/psychiatric-screening.

Mirrors test_predict_api.py's TestClient conventions. Requires the real
psychiatric-pipeline model artifacts (gitignored binaries) -- marked
model_artifact, same as every other test exercising a real trained model.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from drugsim_predict.api import app

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]

HALOPERIDOL_SMILES = "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


class TestPsychiatricScreeningEndpoint:
    def test_returns_200_with_all_six_signals(self, client) -> None:
        r = client.post("/v1/psychiatric-screening", json={"smiles": HALOPERIDOL_SMILES})
        assert r.status_code == 200
        body = r.json()
        for key in ("drd2", "hrh1", "cyp2d6", "bbb", "herg"):
            assert key in body

    def test_herg_is_the_only_validated_signal(self, client) -> None:
        body = client.post("/v1/psychiatric-screening", json={"smiles": HALOPERIDOL_SMILES}).json()
        assert body["herg"]["reliability_tier"] == "validated"
        for key in ("drd2", "hrh1", "cyp2d6", "bbb"):
            assert body[key]["reliability_tier"] == "experimental"

    def test_selectivity_is_present_and_derived_correctly(self, client) -> None:
        body = client.post("/v1/psychiatric-screening", json={"smiles": HALOPERIDOL_SMILES}).json()
        expected = round(body["drd2"]["predicted_pki"] - body["hrh1"]["predicted_pki"], 4)
        assert body["selectivity_index_log10"] == pytest.approx(expected, abs=1e-3)

    def test_overall_caveats_present(self, client) -> None:
        body = client.post("/v1/psychiatric-screening", json={"smiles": HALOPERIDOL_SMILES}).json()
        assert len(body["overall_caveats"]) >= 1
        assert "non-clinical research" in " ".join(body["overall_caveats"]).lower()

    def test_invalid_structure_returns_422(self, client) -> None:
        r = client.post("/v1/psychiatric-screening", json={"smiles": "not a valid smiles!!!"})
        assert r.status_code == 422
        assert r.json()["type"].endswith("invalid-structure")

    def test_empty_smiles_rejected_by_schema(self, client) -> None:
        r = client.post("/v1/psychiatric-screening", json={"smiles": ""})
        assert r.status_code == 422

    def test_extra_fields_rejected(self, client) -> None:
        r = client.post("/v1/psychiatric-screening", json={"smiles": HALOPERIDOL_SMILES, "endpoint": "herg_inhibition"})
        assert r.status_code == 422
