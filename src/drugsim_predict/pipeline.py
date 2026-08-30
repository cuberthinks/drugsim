"""The single reproducible inference pipeline (TDS Sec 6.6).

Five ordered stages, matching the TDS exactly:
    1. Feature computation — via ``drugsim_chem``, unchanged from training.
    2. Model load — the cached, checksum-verified :class:`ModelBundle`.
    3. Feature-set assertion — a freshly computed ``feature_set_id`` must
       equal the one recorded at training time. Mismatch is a hard error.
    4. Uncertainty — conformal interval + applicability-domain assessment.
    5. Envelope assembly — a prediction is never returned without a
       complete reliability block.

No chemistry rule here is new. Parsing, standardisation, descriptors, and
the fingerprint all come from ``drugsim_chem`` exactly as Phase 2/3 built
and Phase 3/4 validated them. This module's only job is orchestration plus
the handful of TDS Sec 5.4 input-acceptance rules (polymer/Markush
rejection, molecular-weight ceiling, mixture rejection) that belong at the
serving boundary, not inside the shared chemistry library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal, Optional

import numpy as np

from drugsim_chem import compute_morgan_fingerprint, process_structure
from drugsim_chem.parsing import StructureFormat, parse_molecule
from drugsim_core.errors import EndpointNotAvailableError, ReproducibilityError, StructureError
from drugsim_core.version import get_rdkit_version
from drugsim_features import compute_feature_set_id
from drugsim_identity import CompoundIdentityResult, load_identity_snapshot, resolve_identity

from drugsim_predict.applicability_domain import ApplicabilityDomainResult, assess_applicability_domain
from drugsim_predict.conformal import ConformalResult, compute_conformal_set
from drugsim_predict.model_registry import DEFAULT_MODEL_ID, ModelBundle, get_model_bundle
from drugsim_predict.settings import get_predict_settings

#: The only ``final_report_status`` values allowed to serve normal
#: predictions (Phase 9 Sec 14 promotion gate). ``EXPERIMENTAL`` and
#: ``REJECTED`` models may still be registered and loaded for internal
#: inspection (e.g. by scripts, or a future internal-only research view),
#: but never reachable through this pipeline's normal inference path.
SERVABLE_STATUSES = frozenset({"VALIDATED FOR INTERNAL RESEARCH"})

__all__ = ["SERVABLE_STATUSES", "InferenceWarning", "PredictionResult", "run_inference"]

Severity = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class InferenceWarning:
    """A structured warning attached to a prediction (never silently dropped)."""

    code: str
    severity: Severity
    message: str
    field: str


@dataclass(frozen=True)
class PredictionResult:
    """The complete, internally-consistent result of one inference call.

    Never constructed with an incomplete reliability block — if conformal
    or applicability-domain assessment cannot be computed, the pipeline
    raises rather than returning a partial result (TDS Sec 6.6 stage 5).
    """

    input_structure: str
    input_format: str
    canonical_smiles: str
    isomeric_smiles: str
    standardized_smiles: str
    inchikey_full: str
    molecular_formula: str
    molecular_weight: float
    identity: CompoundIdentityResult
    predicted_label: str
    predicted_probability_blocker: float
    predicted_probability: float
    conformal: ConformalResult
    applicability_domain: ApplicabilityDomainResult
    warnings: list[InferenceWarning] = field(default_factory=list)

    model_id: str = ""
    model_version: str = ""
    dataset_version: str = ""
    feature_set_id: str = ""
    training_set_size: int = 0
    inference_timestamp: str = ""


@lru_cache(maxsize=1)
def _get_identity_snapshot() -> dict:
    """Load the offline compound-identity snapshot once per process.

    Mirrors :func:`get_model_bundle`'s load-once-and-reuse pattern. A
    missing snapshot file resolves to an empty dict (every compound
    "unidentified"), never a startup failure.
    """
    return load_identity_snapshot(get_predict_settings().compound_identity_snapshot_path)


def _check_feature_set_id(bundle: ModelBundle) -> None:
    """Assert the serving environment's feature identity matches training's.

    Raises:
        ReproducibilityError: If the freshly computed ``feature_set_id``
            (from the currently installed RDKit/drugsim_chem) does not match
            the one the model was trained under. TDS Sec 6.6 stage 3: this
            must raise, never warn — a mismatch means silently wrong
            predictions at scale.
    """
    current = compute_feature_set_id(
        descriptor_spec_version=bundle.descriptor_spec_version,
        rdkit_version=str(get_rdkit_version()),
        standardization_pipeline_version=bundle.standardization_pipeline_version,
        descriptor_names=[*bundle.descriptor_fields, "morgan_fp_r2_2048"],
    )
    if current != bundle.feature_set_id:
        msg = "Serving-time feature_set_id does not match the model's training feature_set_id"
        raise ReproducibilityError(msg, expected=bundle.feature_set_id, actual=current)


def run_inference(
    structure: str,
    fmt: StructureFormat = "smiles",
    *,
    model_id: str = DEFAULT_MODEL_ID,
    bundle: Optional[ModelBundle] = None,
) -> PredictionResult:
    """Run the full, reproducible inference pipeline on one structure.

    Args:
        structure: The raw input structure text.
        fmt: Input format — ``smiles``, ``molblock``, or ``inchi`` (the
            formats ``drugsim_chem.parsing`` supports; the TDS names the
            same three for ``POST /v1/predictions``).
        model_id: Which registered endpoint to run, e.g.
            ``"herg_inhibition"`` (the default, unchanged from before
            Phase 9) or ``"cyp3a4_inhibition"``. Ignored if ``bundle`` is
            given directly.
        bundle: Override the cached model bundle (tests only).

    Returns:
        The complete prediction result, always with a full reliability block.

    Raises:
        StructureError: Empty input, oversized input, unparseable/
            unsanitisable chemistry, a polymer/Markush wildcard atom, a
            mixture with no single dominant fragment, or molecular weight
            above the configured ceiling. This is the "reject cleanly"
            signal the API layer maps to a 422 response — never a 500, and
            never a silently-produced prediction for chemistry the pipeline
            cannot credibly handle.
        ReproducibilityError: The serving environment's computed
            feature_set_id does not match the model's training
            feature_set_id (TDS Sec 6.6 stage 3) — a hard-stop signal that
            something about the toolchain has drifted since training.
        UnknownEndpointError: ``model_id`` has no registry entry.
        EndpointNotAvailableError: ``model_id`` is registered but has not
            passed the Phase 9 Sec 14 promotion gate (i.e. its
            ``final_report_status`` is not ``"VALIDATED FOR INTERNAL
            RESEARCH"``) — it must not be reachable as a normal prediction.
    """
    settings = get_predict_settings()
    bundle = bundle or get_model_bundle(model_id)

    if bundle.final_report_status not in SERVABLE_STATUSES:
        msg = (
            f"Endpoint {bundle.model_id!r} is registered with status "
            f"{bundle.final_report_status!r}, not a status eligible to serve "
            "normal predictions."
        )
        raise EndpointNotAvailableError(msg, model_id=bundle.model_id, final_report_status=bundle.final_report_status)

    if not structure or not structure.strip():
        msg = "empty structure"
        raise StructureError(msg, fmt=fmt)
    if len(structure) > settings.max_smiles_length:
        msg = f"structure exceeds the {settings.max_smiles_length}-character limit"
        raise StructureError(msg, fmt=fmt)

    # Stage 3 (feature-set assertion) is checked before any chemistry work:
    # if the toolchain has drifted, nothing downstream can be trusted either.
    _check_feature_set_id(bundle)

    # Stage 1: parsing + standardisation, unchanged from drugsim_chem.
    processed = process_structure(structure, fmt)

    # TDS Sec 5.4 rule 2: reject classes the model was never trained to
    # represent meaningfully, rather than silently predicting on them.
    mol = parse_molecule(processed.standardized_smiles)
    if any(atom.GetAtomicNum() == 0 for atom in mol.GetAtoms()):
        msg = "polymer/Markush structures (wildcard '*' atoms) are not supported"
        raise StructureError(msg, fmt=fmt)
    if processed.is_mixture:
        msg = "structure is a mixture with no single dominant fragment; cannot generate a well-defined prediction"
        raise StructureError(msg, fmt=fmt)
    if processed.descriptors is None:
        # Should be unreachable once is_mixture is False (see drugsim_chem.pipeline),
        # but never silently proceed without descriptors -- fail loudly instead.
        msg = "physicochemical descriptors could not be computed for this structure"
        raise StructureError(msg, fmt=fmt)
    if processed.descriptors.mw_g_mol > settings.max_molecular_weight:
        msg = f"molecular weight {processed.descriptors.mw_g_mol:.1f} Da exceeds the {settings.max_molecular_weight:.0f} Da limit"
        raise StructureError(msg, fmt=fmt)

    # Identity resolution: a local, in-memory dict lookup only (see
    # drugsim_identity's module docstring for why this is never a live
    # third-party call). Runs only once a structure has passed every
    # rejection gate above, and never blocks or fails prediction -- a
    # compound outside the snapshot resolves as "unidentified", the
    # expected outcome for a novel molecule, not an error.
    identity_result = resolve_identity(processed.identity.inchikey_full, _get_identity_snapshot())

    warnings: list[InferenceWarning] = []
    if processed.stereo_completeness in ("undefined", "partially_defined"):
        warnings.append(
            InferenceWarning(
                code="undefined_stereochemistry",
                severity="medium",
                message=(
                    "One or more stereocentres are undefined or only partially defined. "
                    "The model predicts on the structure exactly as given, without stereoisomer "
                    "enumeration (an unresolved policy question per Phase 1 Step 4 Sec 2.3) -- "
                    "stereoisomers of this compound can differ substantially in potency."
                ),
                field="canonical_representation",
            )
        )

    # Stage 1 (continued): exact training feature layout -- descriptors in
    # the model's recorded field order, concatenated with the fingerprint.
    descriptors_vec = np.array(
        [getattr(processed.descriptors, f) or 0.0 for f in bundle.descriptor_fields]
    )
    fingerprint_vec = compute_morgan_fingerprint(mol)
    feature_vec = np.concatenate([descriptors_vec, fingerprint_vec]).reshape(1, -1)

    # Stage 2: run the registered, already-loaded model.
    class_probabilities = bundle.sklearn_model.predict_proba(feature_vec)[0]
    predicted_label = (
        bundle.positive_class_label if class_probabilities[1] >= 0.5 else bundle.negative_class_label
    )

    # Stage 4: uncertainty + applicability domain. Both are mandatory --
    # an exception here propagates and no partial result is returned.
    conformal_result = compute_conformal_set(class_probabilities, bundle)
    ad_result = assess_applicability_domain(
        fingerprint_vec, descriptors_vec, processed.identity.bemis_murcko_scaffold, bundle
    )

    if ad_result.verdict == "out_of_domain":
        warnings.append(
            InferenceWarning(
                code="out_of_domain",
                severity="high",
                message=ad_result.rationale + " This prediction is an extrapolation.",
                field="applicability_domain",
            )
        )
    elif ad_result.verdict == "borderline":
        warnings.append(
            InferenceWarning(
                code="borderline_domain",
                severity="medium",
                message=ad_result.rationale,
                field="applicability_domain",
            )
        )
    elif ad_result.verdict == "undeterminable":
        warnings.append(
            InferenceWarning(
                code="applicability_domain_undeterminable",
                severity="high",
                message="Applicability domain could not be assessed for this structure.",
                field="applicability_domain",
            )
        )

    if not conformal_result.is_singleton:
        warnings.append(
            InferenceWarning(
                code="conformal_set_ambiguous",
                severity="medium",
                message=(
                    f"At the nominal confidence level, both {bundle.positive_class_label} and "
                    f"{bundle.negative_class_label} remain plausible for this structure -- the "
                    "model cannot distinguish the classes here with the requested confidence."
                ),
                field="conformal",
            )
        )

    warnings.append(
        InferenceWarning(
            code="small_training_set",
            severity="low",
            message=(
                f"Model trained on {bundle.training_set_size} compounds. Interval/coverage "
                "properties reflect this limitation, and the model is classified "
                f"'{bundle.final_report_status}', not clinically validated."
            ),
            field="provenance",
        )
    )

    # Stage 5: envelope assembly. Every field below is already populated;
    # constructing PredictionResult here is what makes "no estimate without
    # a complete reliability block" true by construction, not by convention.
    return PredictionResult(
        input_structure=structure,
        input_format=fmt,
        canonical_smiles=processed.identity.canonical_smiles,
        isomeric_smiles=processed.identity.isomeric_smiles,
        standardized_smiles=processed.standardized_smiles,
        inchikey_full=processed.identity.inchikey_full,
        molecular_formula=processed.identity.molecular_formula,
        molecular_weight=round(float(processed.descriptors.mw_g_mol), 2),
        identity=identity_result,
        predicted_label=predicted_label,
        predicted_probability_blocker=round(float(class_probabilities[1]), 4),
        predicted_probability=round(float(class_probabilities[1]), 4),
        conformal=conformal_result,
        applicability_domain=ad_result,
        warnings=warnings,
        model_id=bundle.model_id,
        model_version=bundle.model_version,
        dataset_version=bundle.dataset_version,
        feature_set_id=bundle.feature_set_id,
        training_set_size=bundle.training_set_size,
        inference_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
