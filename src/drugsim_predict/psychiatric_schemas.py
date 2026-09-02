"""Request/response contract for POST /v1/psychiatric-screening.

A separate, additive schema module rather than extending
:mod:`drugsim_predict.schemas` -- this endpoint's shape (six combined
signals, three regression + selectivity + classification, each with its
own honest `reliability_tier`) has no overlap with the existing
classification-only `PredictionResponse`, and keeping it separate means
nothing here can accidentally widen or weaken that contract.

Deliberately outside the `final_report_status`-gated `run_inference`
promotion path (see `psychiatric_pipeline.py`'s module docstring) -- this
endpoint's own response schema is what makes that explicit to callers,
by requiring `reliability_tier` on every signal rather than presenting a
uniform "prediction" shape that would imply uniform trust.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ClassificationSignalSchema",
    "PsychiatricScreeningRequest",
    "PsychiatricScreeningResponse",
    "RegressionSignalSchema",
]

ReliabilityTierLiteral = Literal["validated", "experimental", "unavailable"]
ADVerdictLiteral = Literal["in_domain", "borderline", "out_of_domain", "undeterminable"]


class PsychiatricScreeningRequest(BaseModel):
    """``POST /v1/psychiatric-screening`` request body."""

    model_config = ConfigDict(extra="forbid")

    smiles: str = Field(min_length=1, max_length=6_000, description="The structure to screen, as SMILES.")


class RegressionSignalSchema(BaseModel):
    """DRD2 or HRH1 -- a continuous predicted binding-affinity signal."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str
    reliability_tier: ReliabilityTierLiteral
    predicted_pki: float = Field(description="Predicted pKi; higher = stronger predicted binding.")
    uncertainty_half_width_pki: float = Field(description="Split-conformal interval half-width, in pKi units, at 90% nominal confidence.")
    applicability_domain_verdict: ADVerdictLiteral
    caveat: Optional[str] = None


class ClassificationSignalSchema(BaseModel):
    """CYP2D6, BBB, or hERG -- a binary classification signal."""

    model_config = ConfigDict(extra="forbid")

    endpoint: str
    reliability_tier: ReliabilityTierLiteral
    predicted_label: str
    predicted_probability: float
    conformal_set: list[str] = Field(description="Class label(s) still plausible at the nominal confidence level. A set of size 2 means the model cannot distinguish the classes for this input.")
    conformal_is_singleton: bool
    applicability_domain_verdict: ADVerdictLiteral
    applicability_domain_rationale: str
    caveat: Optional[str] = None


class PsychiatricScreeningResponse(BaseModel):
    """``POST /v1/psychiatric-screening`` (200) response body.

    No `id`/audit-log persistence (unlike `PredictionResponse`) -- this
    endpoint is explicitly a research/screening tool, not part of the
    persisted prediction-history surface `GET /predict/{id}` serves.
    """

    model_config = ConfigDict(extra="forbid")

    smiles: str
    drd2: RegressionSignalSchema
    hrh1: RegressionSignalSchema
    selectivity_index_log10: float
    selectivity_fold_for_drd2: float
    selectivity_interpretation: str
    selectivity_domain_status: str
    cyp2d6: ClassificationSignalSchema
    bbb: ClassificationSignalSchema
    herg: ClassificationSignalSchema
    overall_caveats: list[str]
    inference_timestamp: str
