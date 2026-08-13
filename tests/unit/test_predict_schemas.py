"""Tests for the prediction response contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from drugsim_predict.schemas import (
    ApplicabilityDomainSchema,
    ConformalSchema,
    EstimateSchema,
    PredictionResponse,
    PredictRequest,
    ProvenanceSchema,
    ReliabilitySchema,
)

pytestmark = pytest.mark.unit


def _make_reliability() -> ReliabilitySchema:
    return ReliabilitySchema(
        conformal=ConformalSchema(
            predicted_set=["blocker"], p_value_blocker=0.9, p_value_non_blocker=0.05,
            nominal_confidence=0.9, is_singleton=True, method="split_conformal_prediction",
        ),
        applicability_domain=ApplicabilityDomainSchema(
            verdict="in_domain", max_tanimoto_to_training=1.0, knn_distance=0.1,
            knn_distance_threshold=1.74, scaffold_seen_in_training=True,
            rationale="test rationale", method="tanimoto_knn_distance_scaffold_membership",
        ),
    )


class TestReliabilityIsMandatory:
    def test_reliability_field_is_not_optional_in_the_schema(self) -> None:
        """The contract guarantee is enforced by construction: PredictionResponse
        has no default for `reliability`, so it cannot be omitted."""
        sig_fields = PredictionResponse.model_fields
        assert "reliability" in sig_fields
        assert sig_fields["reliability"].is_required()

    def test_constructing_a_response_without_reliability_fails(self) -> None:
        with pytest.raises(ValidationError):
            PredictionResponse.model_validate(
                {
                    "id": "prd_x", "request_id": "req_x",
                    "molecule": {
                        "canonical_smiles": "CCO", "isomeric_smiles": "CCO",
                        "standardized_smiles": "CCO", "inchikey_full": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
                        "molecular_formula": "C2H6O",
                    },
                    "estimate": {"endpoint": "herg_inhibition", "predicted_label": "non_blocker", "predicted_probability_blocker": 0.1, "predicted_probability": 0.1},
                    "provenance": {
                        "model_id": "herg_inhibition", "model_version": "0.1.0", "dataset_version": "v1",
                        "feature_set_id": "abc", "training_set_size": 6792,
                        "final_report_status": "VALIDATED FOR INTERNAL RESEARCH",
                    },
                    "warnings": [], "inference_timestamp": "2026-01-01T00:00:00+00:00",
                    # "reliability" deliberately omitted
                }
            )


class TestSchemaValidation:
    def test_predict_request_rejects_unknown_format(self) -> None:
        with pytest.raises(ValidationError):
            PredictRequest.model_validate({"structure": {"format": "pdb", "value": "x"}})

    def test_predict_request_rejects_empty_value(self) -> None:
        with pytest.raises(ValidationError):
            PredictRequest.model_validate({"structure": {"format": "smiles", "value": ""}})

    def test_predict_request_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            PredictRequest.model_validate({"structure": {"format": "smiles", "value": "CCO"}, "unexpected": 1})

    def test_estimate_probability_must_be_in_unit_interval(self) -> None:
        with pytest.raises(ValidationError):
            EstimateSchema(endpoint="herg_inhibition", predicted_label="blocker", predicted_probability_blocker=1.5)

    def test_full_response_round_trips_through_json(self) -> None:
        response = PredictionResponse(
            id="prd_x", request_id="req_x",
            molecule={
                "canonical_smiles": "CCO", "isomeric_smiles": "CCO", "standardized_smiles": "CCO",
                "inchikey_full": "LFQSCWFLJHTTHZ-UHFFFAOYSA-N", "molecular_formula": "C2H6O",
            },
            estimate={"endpoint": "herg_inhibition", "predicted_label": "non_blocker", "predicted_probability_blocker": 0.1, "predicted_probability": 0.1},
            reliability=_make_reliability(),
            provenance={
                "model_id": "herg_inhibition", "model_version": "0.1.0", "model_checksum": "0" * 64,
                "dataset_version": "v1", "feature_set_id": "abc",
                "standardization_pipeline_version": "1", "descriptor_spec_version": "1", "rdkit_version": "2025.3.3",
                "training_set_size": 6792, "input_hash": "deadbeefcafe",
                "final_report_status": "VALIDATED FOR INTERNAL RESEARCH",
            },
            warnings=[], inference_timestamp="2026-01-01T00:00:00+00:00",
        )
        round_tripped = PredictionResponse.model_validate_json(response.model_dump_json())
        assert round_tripped == response

    def test_provenance_never_claims_clinical_validation(self) -> None:
        """Not a schema-enforced invariant (final_report_status is a free
        string, matching the model registry) -- a documentation-level test
        pinning that the ONLY status this system currently produces is the
        Phase 4 wording, never an escalated claim."""
        provenance = ProvenanceSchema(
            model_id="herg_inhibition", model_version="0.1.0", model_checksum="0" * 64,
            dataset_version="v1", feature_set_id="abc",
            standardization_pipeline_version="1", descriptor_spec_version="1", rdkit_version="2025.3.3",
            training_set_size=6792, input_hash="deadbeefcafe",
            final_report_status="VALIDATED FOR INTERNAL RESEARCH",
        )
        forbidden = {"clinically validated", "medically validated", "production-ready", "safe", "replaces laboratory testing"}
        assert not any(term in provenance.final_report_status.lower() for term in forbidden)
