"""The prediction request/response contract.

Adapted from the envelope shape in TDS Sec 5.4/5.9 (``estimate`` +
``reliability`` + ``provenance`` + ``warnings``) to this phase's minimal
internal-service scope — no multi-tenant auth, no async job queue, no
multi-endpoint batch request (see ``docs/phase5/phase5-prediction-engine.md``
for why: those require infrastructure — Keycloak, a message queue,
multi-tenant Postgres — that does not exist in this environment and is out
of this phase's explicit "minimal internal API" scope).

**Contract guarantee, enforced by construction**: :class:`PredictionResponse`
has no optional ``reliability`` field. A response cannot be built without
one, matching the TDS Sec 5.9 invariant ("no prediction response contains
`estimate` without a complete `reliability` block") even though the formal
contract-test harness described there (Schemathesis, OpenAPI-driven) is not
set up in this phase — the invariant is real here, just verified by the
type system and by ``tests/unit/test_predict_schemas.py`` rather than by a
generated fuzz suite.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApplicabilityDomainSchema",
    "ConformalSchema",
    "EndpointListItem",
    "EndpointsResponse",
    "ErrorDetail",
    "EstimateSchema",
    "HealthResponse",
    "ModelDetailResponse",
    "MoleculeSchema",
    "PredictionResponse",
    "PredictRequest",
    "ProblemDetail",
    "ProvenanceSchema",
    "ReliabilitySchema",
    "StructureInput",
    "WarningSchema",
]

StructureFormatLiteral = Literal["smiles", "molblock", "inchi"]
ADVerdictLiteral = Literal["in_domain", "borderline", "out_of_domain", "undeterminable"]
SeverityLiteral = Literal["low", "medium", "high"]


class StructureInput(BaseModel):
    """One molecular structure, in one of the TDS-approved formats."""

    model_config = ConfigDict(extra="forbid")

    format: StructureFormatLiteral = Field(description="smiles | molblock | inchi")
    # 6,000 -- a small margin over PredictSettings.max_smiles_length (5,000,
    # the actually-enforced business rule in pipeline.py, checked before any
    # RDKit parsing). Phase 7 audit finding: this was previously 100,000,
    # a schema-level ceiling 20x more permissive than the real one, so the
    # OpenAPI-documented limit didn't reflect what the service would ever
    # accept. Not a DoS fix (the pipeline's cheap length check already ran
    # before any expensive work either way) -- a documentation-accuracy fix.
    value: str = Field(min_length=1, max_length=6_000, description="The structure text")


class PredictRequest(BaseModel):
    """``POST /predict`` request body."""

    model_config = ConfigDict(extra="forbid")

    structure: StructureInput
    # Phase 9: optional, defaults to the original (and, before Phase 9, only)
    # endpoint -- an existing client that has never heard of "endpoint"
    # keeps getting exactly the hERG behaviour it always has.
    endpoint: str = Field(default="herg_inhibition", description="Which registered endpoint to run, e.g. 'herg_inhibition' or 'cyp3a4_inhibition'.")


class WarningSchema(BaseModel):
    """A structured warning — never a bare string, so a client can filter
    or escalate on ``severity``/``code`` programmatically."""

    model_config = ConfigDict(extra="forbid")

    code: str
    severity: SeverityLiteral
    message: str
    field: str


class MoleculeSchema(BaseModel):
    """The canonical molecule representation, computed once by
    ``drugsim_chem`` and never recomputed differently downstream."""

    model_config = ConfigDict(extra="forbid")

    canonical_smiles: str
    isomeric_smiles: str
    standardized_smiles: str
    inchikey_full: str
    molecular_formula: str


class EstimateSchema(BaseModel):
    """The prediction itself — deliberately thin. Uncertainty lives in
    ``reliability``, never folded into this block, so a client cannot
    render ``estimate`` alone and accidentally omit the caveats."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str = Field(description="e.g. 'herg_inhibition'")
    # Phase 9: widened from Literal["blocker", "non_blocker"] to a plain str
    # so other endpoints can use their own label vocabulary (e.g. CYP3A4's
    # "inhibitor"/"non_inhibitor"). A type-only relaxation -- hERG responses
    # still contain exactly the same two string values they always did.
    predicted_label: str
    predicted_probability_blocker: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description=(
            "Legacy hERG-specific field name, populated only for endpoint='herg_inhibition' "
            "(null otherwise) so existing hERG clients keep working unchanged. "
            "Raw model output. NOT a calibrated probability outside conditions resembling "
            "the training population (~66% blocker prevalence) -- see reliability.conformal "
            "for the validated uncertainty statement, and phase4-reliability-report.md Sec "
            "'Reliability' for the calibration-under-shift finding."
        ),
    )
    predicted_probability: float = Field(
        ge=0.0, le=1.0,
        description=(
            "Raw model output: probability of the endpoint's positive-class label "
            "(see 'predicted_label' and the endpoint's own definition). Generic field, "
            "populated for every endpoint including hERG -- prefer this over the legacy "
            "'predicted_probability_blocker' field for any endpoint other than hERG."
        ),
    )


class ConformalSchema(BaseModel):
    """Split conformal prediction set (TDS Sec 6.7).

    ``predicted_set`` is a MARGINAL, population-level coverage guarantee,
    not a per-instance correctness probability -- see
    ``drugsim_predict.conformal`` module docstring.
    """

    model_config = ConfigDict(extra="forbid")

    # Phase 9: widened from list[Literal["blocker", "non_blocker"]] to
    # list[str] -- see EstimateSchema.predicted_label's note; same
    # type-only relaxation, same hERG-unchanged guarantee.
    predicted_set: list[str]
    p_value_blocker: float
    p_value_non_blocker: float
    nominal_confidence: float
    is_singleton: bool
    method: str = Field(
        description="Phase 10: names the uncertainty methodology (e.g. 'split_conformal_prediction') "
        "so a prediction is traceable to its method from its own response, without a separate registry lookup."
    )


class ApplicabilityDomainSchema(BaseModel):
    """Applicability-domain verdict and evidence (TDS Sec 6.8)."""

    model_config = ConfigDict(extra="forbid")

    verdict: ADVerdictLiteral
    max_tanimoto_to_training: Optional[float] = None
    knn_distance: Optional[float] = None
    knn_distance_threshold: float
    scaffold_seen_in_training: Optional[bool] = None
    rationale: str
    method: str = Field(
        description="Phase 10: names the applicability-domain methodology so a prediction is "
        "traceable to its method from its own response, without a separate registry lookup."
    )


class ReliabilitySchema(BaseModel):
    """Mandatory on every prediction response — see module docstring."""

    model_config = ConfigDict(extra="forbid")

    conformal: ConformalSchema
    applicability_domain: ApplicabilityDomainSchema


class ProvenanceSchema(BaseModel):
    """Everything needed to know exactly which model/data/toolchain produced
    this, and to reproduce it -- Phase 7 hardening requirement: a prediction
    must be reproducible from its own recorded metadata, without needing
    separate access to the model registry file."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_version: str
    model_checksum: str = Field(description="SHA-256 of the exact model artifact file, verified at load time.")
    dataset_version: str
    feature_set_id: str
    standardization_pipeline_version: str
    descriptor_spec_version: str
    rdkit_version: str
    training_set_size: int
    input_hash: str = Field(
        description="Non-reversible digest of the submitted structure -- lets this response be "
        "correlated with the server-side audit log without ever exposing the structure itself."
    )
    final_report_status: str = Field(
        description="The Phase 4 classification, e.g. 'VALIDATED FOR INTERNAL RESEARCH' -- "
        "never 'clinically validated' or 'production-ready'"
    )


class PredictionResponse(BaseModel):
    """``POST /predict`` (200) and ``GET /predict/{id}`` (200) response body."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Prediction public ID, e.g. 'prd_01J8XK...'")
    request_id: str
    molecule: MoleculeSchema
    estimate: EstimateSchema
    reliability: ReliabilitySchema
    provenance: ProvenanceSchema
    warnings: list[WarningSchema]
    inference_timestamp: str
    status: Literal["complete"] = "complete"


class ErrorDetail(BaseModel):
    """One field-level error, nested in :class:`ProblemDetail.errors`."""

    model_config = ConfigDict(extra="forbid")

    field: Optional[str] = None
    code: str
    message: str


class ProblemDetail(BaseModel):
    """RFC 9457 ``application/problem+json``, matching TDS Sec 5.3 exactly."""

    model_config = ConfigDict(extra="forbid")

    type: str
    title: str
    status: int
    detail: str
    instance: Optional[str] = None
    request_id: Optional[str] = None
    errors: Optional[list[ErrorDetail]] = None


class HealthResponse(BaseModel):
    """``GET /health`` response — liveness only, no dependency checks
    (TDS Sec 5.8: liveness must not check dependencies)."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = "ok"


class EndpointListItem(BaseModel):
    """One registered endpoint's discovery metadata (Phase 9 Sec 17: lets a
    client distinguish available/experimental/unavailable without having to
    attempt a prediction and inspect the failure)."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    endpoint_name: str
    category: Optional[str] = None
    final_report_status: str
    dataset_version: str
    training_set_size: Optional[int] = None
    servable: bool = Field(description="Whether POST /predict will currently accept this endpoint.")


class EndpointsResponse(BaseModel):
    """``GET /endpoints`` response — every registered endpoint, regardless
    of promotion status; ``servable`` on each item is the actionable signal."""

    model_config = ConfigDict(extra="forbid")

    endpoints: list[EndpointListItem]


class ModelDetailResponse(BaseModel):
    """``GET /model`` / ``GET /model/latest`` response."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    model_version: str
    model_checksum: str = Field(description="SHA-256 of the exact model artifact file, verified at load time.")
    endpoint: str
    dataset_version: str
    algorithm: str
    training_set_size: int
    feature_set_id: str
    standardization_pipeline_version: str
    descriptor_spec_version: str
    rdkit_version: str
    final_report_status: str
    global_split_test_roc_auc: Optional[float] = None
