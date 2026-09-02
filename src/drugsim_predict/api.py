"""The minimal internal prediction API.

Endpoints, per the Phase 5 brief's explicit minimal scope (not the TDS's
full multi-tenant ``/v1/predictions`` async-job surface — see
``docs/phase5/phase5-prediction-engine.md`` for why that is out of scope
here): ``POST /predict``, ``GET /predict/{id}``, ``GET /health``,
``GET /model``, ``GET /model/latest``. ``GET /health/ready`` is added
beyond the explicit list because the TDS specifies it (Sec 5.8) and it is
what lets a deployment orchestrator detect a broken model load without any
additional scope — liveness alone cannot do that.

Authentication: a single shared API key (or small set of keys), checked by
:mod:`drugsim_predict.security`, gates every route except health checks and
API docs -- NOT the TDS's full multi-tenant OIDC design (Sec 5.2, which
resolves to ``(user_id, tenant_id, roles)`` and requires infrastructure --
Keycloak, multi-tenant Postgres -- not present in this environment). This
is the minimum viable access control for a controlled external
demonstration with a small, known set of users, not a real identity
platform; there is still no per-user data model (a name, an account, a
role). Documented as a limitation in docs/phase8, not silently omitted.

Confidentiality audit (2026-08-22): ``GET /predict/{id}`` IS now scoped to
the API key that created a prediction (see that handler's own docstring
and store.py) -- the smallest unit of "who" this codebase can express.
Two different callers sharing the same configured key (e.g. every visitor
to the one public frontend deployment, which bakes in a single key) are
still not isolated from each other -- that requires actually issuing
distinct keys per caller, an operational/deployment decision this code
does not make for you. What this closes is the case that had NO scoping
at all: any one of several *distinct* configured keys being able to read
data created under any other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncio
import os
import time

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from drugsim_core.errors import EndpointNotAvailableError, IntegrityError, ReproducibilityError, StructureError, UnknownEndpointError
from drugsim_core.ids import generate_ulid, public_id
from drugsim_core.logging import configure_logging
from drugsim_core.redaction import structure_digest

from drugsim_predict.model_registry import DEFAULT_MODEL_ID, ModelBundle, get_model_bundle, list_registered_endpoints
from drugsim_predict.pipeline import SERVABLE_STATUSES, PredictionResult, run_inference
from drugsim_predict.psychiatric_pipeline import run_psychiatric_screening
from drugsim_predict.psychiatric_schemas import PsychiatricScreeningRequest, PsychiatricScreeningResponse
from drugsim_predict.schemas import (
    ApplicabilityDomainSchema,
    CompoundIdentitySchema,
    ConformalSchema,
    EndpointListItem,
    EndpointsResponse,
    EstimateSchema,
    ErrorDetail,
    HealthResponse,
    ModelDetailResponse,
    MoleculeSchema,
    PredictionResponse,
    PredictRequest,
    ProblemDetail,
    ProvenanceSchema,
    ReliabilitySchema,
    WarningSchema,
)
from drugsim_predict.security import (
    ApiKeyMiddleware,
    BodySizeLimitMiddleware,
    ConcurrencyLimitMiddleware,
    RateLimitMiddleware,
)
from drugsim_predict.settings import assert_safe_to_start, get_predict_settings
from drugsim_predict.store import PredictionStore

__all__ = ["app"]

# Wired here (not left to the caller's process entrypoint) so the structlog
# redaction processor (drugsim_core.redaction.redact_event) is active for
# every log line this service emits, including ones from third-party/stdlib
# loggers routed through the same chain. Phase 7 audit finding: this service
# previously ran under structlog's unconfigured default, meaning the
# redaction processor built for exactly this service was never actually in
# the active chain — see docs/phase7 for the finding. configure_logging()
# is idempotent, so this is safe even if a caller also configures it
# explicitly before import.
configure_logging(level=os.environ.get("DRUGSIM_LOG_LEVEL", "INFO"), fmt=os.environ.get("DRUGSIM_LOG_FORMAT", "json"))

log = structlog.get_logger(__name__)

_settings = get_predict_settings()

# Phase 8: refuses to start an unauthenticated staging/production deployment
# rather than silently serving one -- see settings.assert_safe_to_start.
assert_safe_to_start(_settings)

app = FastAPI(
    title="DrugSim Prediction Engine",
    description=(
        "Multi-endpoint ADMET prediction service. Serves only endpoints registered with "
        "final_report_status='VALIDATED FOR INTERNAL RESEARCH' -- see GET /endpoints for what's "
        "currently available. Started with hERG inhibition (Phase 4); Phase 9 added CYP3A4 inhibition."
    ),
    version="0.1.0",
)

# Middleware order matters (Starlette: the LAST middleware added is the
# OUTERMOST -- it sees a request first and a response last). Desired order,
# outermost to innermost:
#   CORS -> body size -> API key -> rate limit -> concurrency -> routes
# CORS must be outermost so a browser's preflight OPTIONS request (which
# never carries X-API-Key) is answered before it ever reaches the API-key
# gate -- added last, below, for exactly that reason. Within the app's own
# middlewares, the cheapest/broadest check (body size) goes first, the most
# expensive-to-recover-from (concurrency, guarding real compute) goes last.
app.add_middleware(ConcurrencyLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(ApiKeyMiddleware)
app.add_middleware(BodySizeLimitMiddleware)

# The frontend is a separate origin (Vite dev server / static host, or a
# reverse-proxied production domain). Defaults cover local development;
# production origins are supplied via DRUGSIM_PREDICT_CORS_ALLOWED_ORIGINS
# so this service is never opened up more broadly than a deployment
# explicitly configures -- see docs/phase8 for the production value.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

_store: Optional[PredictionStore] = None


def get_store() -> PredictionStore:
    """FastAPI dependency for the prediction store.

    A module-level singleton by default (one SQLite connection pool for the
    process), but overridable via ``app.dependency_overrides[get_store]`` in
    tests for a temp-file or in-memory store without touching env vars or
    the real ``var/predictions.sqlite3``.
    """
    global _store
    if _store is None:
        _store = PredictionStore()
    return _store


def _result_to_response(prediction_id: str, request_id: str, result: PredictionResult, input_hash: str) -> PredictionResponse:
    # Phase 9: the bundle that actually produced `result` -- keyed by
    # result.model_id, NOT the no-arg hERG default, so a CYP3A4 prediction's
    # provenance is never silently filled in from the hERG bundle. This is
    # a cache hit (the pipeline already loaded and cached this exact bundle
    # to run inference), never a second disk read.
    bundle = get_model_bundle(result.model_id)
    return PredictionResponse(
        id=prediction_id,
        request_id=request_id,
        molecule=MoleculeSchema(
            canonical_smiles=result.canonical_smiles,
            isomeric_smiles=result.isomeric_smiles,
            standardized_smiles=result.standardized_smiles,
            inchikey_full=result.inchikey_full,
            molecular_formula=result.molecular_formula,
            molecular_weight=result.molecular_weight,
        ),
        compound_identity=CompoundIdentitySchema(
            identity_status=result.identity.identity_status,
            compound_name=result.identity.compound_name,
            synonyms=list(result.identity.synonyms) if result.identity.synonyms else None,
            identifiers=result.identity.identifiers,
            description=result.identity.description,
            description_source=result.identity.description_source,
            source=result.identity.source,
            retrieved_at=result.identity.retrieved_at,
        ),
        estimate=EstimateSchema(
            endpoint=result.model_id,
            predicted_label=result.predicted_label,
            # Legacy field: populated only for hERG, so its meaning ("probability
            # of blocker") never applies to an endpoint where it would be wrong.
            predicted_probability_blocker=result.predicted_probability_blocker if result.model_id == DEFAULT_MODEL_ID else None,
            predicted_probability=result.predicted_probability,
        ),
        reliability=ReliabilitySchema(
            conformal=ConformalSchema(
                predicted_set=list(result.conformal.predicted_set),
                p_value_blocker=result.conformal.p_value_blocker,
                p_value_non_blocker=result.conformal.p_value_non_blocker,
                nominal_confidence=result.conformal.nominal_confidence,
                is_singleton=result.conformal.is_singleton,
                method=result.conformal.method,
            ),
            applicability_domain=ApplicabilityDomainSchema(
                verdict=result.applicability_domain.verdict,
                max_tanimoto_to_training=result.applicability_domain.max_tanimoto_to_training,
                knn_distance=result.applicability_domain.knn_distance,
                knn_distance_threshold=result.applicability_domain.knn_distance_threshold,
                scaffold_seen_in_training=result.applicability_domain.scaffold_seen_in_training,
                rationale=result.applicability_domain.rationale,
                method=result.applicability_domain.method,
            ),
        ),
        provenance=ProvenanceSchema(
            model_id=result.model_id,
            model_version=result.model_version,
            model_checksum=bundle.model_checksum,
            dataset_version=result.dataset_version,
            feature_set_id=result.feature_set_id,
            standardization_pipeline_version=bundle.standardization_pipeline_version,
            descriptor_spec_version=bundle.descriptor_spec_version,
            rdkit_version=bundle.rdkit_version,
            training_set_size=result.training_set_size,
            input_hash=input_hash,
            final_report_status=bundle.final_report_status,
        ),
        warnings=[WarningSchema(code=w.code, severity=w.severity, message=w.message, field=w.field) for w in result.warnings],
        inference_timestamp=result.inference_timestamp,
    )


def _problem(status: int, type_slug: str, title: str, detail: str, request_id: str, errors: Optional[list[ErrorDetail]] = None) -> JSONResponse:
    body = ProblemDetail(
        type=f"https://drugsim.internal/errors/{type_slug}",
        title=title,
        status=status,
        detail=detail,
        request_id=request_id,
        errors=errors,
    )
    return JSONResponse(status_code=status, content=body.model_dump(exclude_none=True), media_type="application/problem+json")


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Schema-level rejections (empty structure, unknown format, extra
    fields) never reach the ``predict`` handler's own try/except -- FastAPI
    intercepts them first. Without this, they would (a) return a
    non-problem+json body, violating TDS Sec 5.1.2, and (b) never be logged,
    violating "every prediction must be logged with... validation status."
    Both are fixed here rather than left as a gap discovered later.
    """
    request_id = getattr(request.state, "request_id", f"req_{generate_ulid()}")
    if request.url.path == "/predict" and request.method == "POST":
        # Best-effort: the raw body may not be valid JSON at all, in which
        # case there is nothing structure-shaped to hash -- log what we can.
        input_hash = "unavailable"
        try:
            body = await request.json()
            value = body.get("structure", {}).get("value")
            if isinstance(value, str):
                input_hash = structure_digest(value)
        except Exception:  # noqa: BLE001 -- best-effort only, never fails the response
            pass
        # Exception handlers run outside normal Depends() resolution, so the
        # override lookup is done manually here -- this is what lets tests
        # redirect this write to an isolated store via
        # app.dependency_overrides[get_store], exactly as route handlers do.
        store_factory = request.app.dependency_overrides.get(get_store, get_store)
        store_factory().record_rejection(
            prediction_id=public_id("prediction"),
            request_id=request_id,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            input_hash=input_hash,
            rejection_reason=f"request_validation_error: {exc.errors()}",
        )
    errors = [
        ErrorDetail(field=".".join(str(p) for p in e["loc"]), code=e["type"], message=e["msg"])
        for e in exc.errors()
    ]
    return _problem(422, "malformed-request", "Request failed validation", "The request body did not match the expected schema", request_id, errors=errors)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler for every route.

    ``/predict`` has its own catch-all (see its handler for the full
    rationale on logging only ``type(exc).__name__``, never ``str(exc)``);
    this is the same safety net for every other route (``/model``,
    ``/model/latest``, ``/predict/{id}``, ``/health/ready``), none of which
    previously had one. Without it, an unexpected exception on those routes
    would reach Starlette's default handler and print an unredacted
    traceback to the process's stderr.
    """
    request_id = getattr(request.state, "request_id", f"req_{generate_ulid()}")
    log.error("request.unexpected_error", request_id=request_id, path=request.url.path, error_type=type(exc).__name__)
    return _problem(500, "internal-error", "An unexpected error occurred", "This has been logged for investigation.", request_id)


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Every request gets a correlation ID, echoed and logged — never the
    raw structure, per the redaction boundary documented in store.py."""
    request_id = request.headers.get("X-Request-Id") or f"req_{generate_ulid()}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness only — no dependency checks (TDS Sec 5.8)."""
    return HealthResponse()


#: A fixed, always-valid molecule for the prediction-engine health check.
#: Ethanol: trivially parses, standardises, and predicts under any version
#: of the model -- this check is about "does the pipeline run end to end",
#: not "what does the model say about this compound."
_HEALTH_CHECK_SMILES = "CCO"


@app.get("/health/ready")
def health_ready(store: PredictionStore = Depends(get_store)) -> JSONResponse:
    """Readiness: application, database, model, and prediction-engine
    checks, per Phase 8 Sec 10.

    Deliberately reports only a per-component ok/unavailable status
    publicly, never the underlying exception text -- a checksum-mismatch
    message embeds a filesystem path, and this endpoint has no API-key
    gate (an orchestrator must be able to poll it), so it must not become a
    path for leaking internal diagnostic detail. The real exception is
    still logged server-side for whoever is on call.

    Note: this service's own audit trail is SQLite, not PostgreSQL --
    see docs/phase8/phase8-deployment-report.md for why drugsim_predict
    does not depend on the platform's Postgres+RDKit database. "database"
    below checks the dependency this service actually has.
    """
    checks: dict[str, str] = {"application": "ok"}

    try:
        # Explicit DEFAULT_MODEL_ID, not a bare call: functools.lru_cache
        # keys on the literal arguments passed, not the resolved default --
        # get_model_bundle() and get_model_bundle(DEFAULT_MODEL_ID) are two
        # DIFFERENT cache entries even though they load the identical model,
        # each holding its own full copy in memory forever (verified: two
        # cache misses, two distinct objects). run_inference() below always
        # resolves and passes its model_id explicitly, so matching that here
        # collapses this endpoint onto the same single cache entry instead
        # of permanently doubling this process's model memory on first use.
        get_model_bundle(DEFAULT_MODEL_ID)
        checks["model"] = "ok"
    except IntegrityError as exc:
        log.error("health.model_unavailable", reason=str(exc))
        checks["model"] = "unavailable"

    try:
        store.ping()
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 -- health check must never itself crash the endpoint
        log.error("health.database_unavailable", error_type=type(exc).__name__)
        checks["database"] = "unavailable"

    if checks["model"] == "ok":
        try:
            run_inference(_HEALTH_CHECK_SMILES, "smiles")
            checks["prediction_engine"] = "ok"
        except Exception as exc:  # noqa: BLE001 -- see database check above
            log.error("health.prediction_engine_unavailable", error_type=type(exc).__name__)
            checks["prediction_engine"] = "unavailable"
    else:
        # Meaningless to attempt an inference against a model that failed
        # its own integrity check -- report it as a consequence of the
        # model check, not a second, confusing independent failure.
        checks["prediction_engine"] = "unavailable"

    overall_ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if overall_ready else 503,
        content={"status": "ready" if overall_ready else "not_ready", "checks": checks},
    )


def _model_detail(bundle: ModelBundle) -> ModelDetailResponse:
    metrics = bundle.registry.get("metrics", {})
    global_split = metrics.get("global_split_test_group_9", {})
    return ModelDetailResponse(
        model_id=bundle.model_id,
        model_version=bundle.model_version,
        model_checksum=bundle.model_checksum,
        endpoint=bundle.model_id,
        dataset_version=bundle.dataset_version,
        algorithm=bundle.algorithm,
        training_set_size=bundle.training_set_size,
        feature_set_id=bundle.feature_set_id,
        standardization_pipeline_version=bundle.standardization_pipeline_version,
        descriptor_spec_version=bundle.descriptor_spec_version,
        rdkit_version=bundle.rdkit_version,
        final_report_status=bundle.final_report_status,
        global_split_test_roc_auc=global_split.get("roc_auc"),
    )


@app.get("/endpoints", response_model=EndpointsResponse)
def get_endpoints() -> EndpointsResponse:
    """Every registered endpoint and its promotion status (Phase 9 Sec 17:
    lets a client distinguish available/experimental/unavailable up front,
    without a failed ``POST /predict`` as the only way to find out).

    Phase 10 correction: an earlier version of this docstring claimed this
    route was "deliberately unauthenticated, like /health" -- that was
    never true. It is not in ``security._PUBLIC_PATHS``, so it correctly
    requires the same ``X-API-Key`` as ``GET /model`` whenever one is
    configured (verified live during the Phase 10 API audit). That is the
    right behaviour for consistency with ``/model``, which exposes
    comparable metadata under the same gate -- the code was already
    correct; only the comment was wrong.
    """
    return EndpointsResponse(
        endpoints=[
            EndpointListItem(
                model_id=e.model_id,
                endpoint_name=e.endpoint_name,
                category=e.category,
                final_report_status=e.final_report_status,
                dataset_version=e.dataset_version,
                training_set_size=e.training_set_size,
                servable=e.final_report_status in SERVABLE_STATUSES,
            )
            for e in list_registered_endpoints()
        ]
    )


@app.get("/model", response_model=ModelDetailResponse)
def get_model(endpoint: str = DEFAULT_MODEL_ID) -> ModelDetailResponse:
    """Detail for a deployed model, defaulting to hERG (unchanged from
    before Phase 9 for any caller that does not pass ``?endpoint=``)."""
    return _model_detail(get_model_bundle(endpoint))


@app.get("/model/latest", response_model=ModelDetailResponse)
def get_model_latest(endpoint: str = DEFAULT_MODEL_ID) -> ModelDetailResponse:
    """Detail for the latest version of a model. A single version per
    endpoint is registered in this phase, so this is currently identical to
    ``GET /model``; kept as a separate endpoint because a future second
    model_version would make them diverge, and callers should not have to
    change which one they call."""
    return _model_detail(get_model_bundle(endpoint))


@app.post("/predict", response_model=PredictionResponse, status_code=200)
async def predict(body: PredictRequest, request: Request, store: PredictionStore = Depends(get_store)) -> JSONResponse:
    """Run inference on one structure. A single Random Forest prediction on
    one compound completes in tens of milliseconds, so the TDS's async-job
    design (built for stereoisomer enumeration across ~20 endpoints and
    batch uploads) is not needed for this phase's single-endpoint, single-
    structure scope — see docs/phase5 for the full reasoning. Every
    response, success or failure, is logged with provenance (store.py).

    Phase 8 hardening: the inference call runs in the thread pool under a
    wall-clock timeout (``PredictSettings.request_timeout_seconds``), per
    the TDS Sec 7.7 "parser hang / catastrophic backtracking" control. This
    is a real, honest limitation short of what that section actually
    specifies (a hard subprocess kill via rlimit/seccomp): a timed-out
    Python thread cannot be forcibly terminated, so a genuinely hung parse
    keeps consuming a thread-pool slot in the background after the client
    has already received a clean error. What this DOES guarantee is that
    no caller is left waiting indefinitely, and that a hang degrades this
    process's capacity rather than hanging the whole event loop. True
    process-level isolation (the TDS's full design, built for large batch
    SDF uploads processed asynchronously) is out of scope for this
    phase's minimal, small-inline-string, synchronous surface — see
    docs/phase8/phase8-deployment-report.md "Known limitations."
    """
    request_id = request.state.request_id
    prediction_id = public_id("prediction")
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    input_hash = structure_digest(body.structure.value)
    # Phase 8 Sec 9 (monitor latency): wall-clock time from request receipt
    # to response, logged on every exit path below -- success or failure --
    # so latency can be aggregated from the log stream without a separate
    # metrics system.
    start_time = time.monotonic()

    def _duration_ms() -> float:
        return round((time.monotonic() - start_time) * 1000, 1)

    log.info("predict.request", request_id=request_id, input_digest=input_hash, format=body.structure.format, endpoint=body.endpoint)

    try:
        result = await asyncio.wait_for(
            run_in_threadpool(run_inference, body.structure.value, body.structure.format, model_id=body.endpoint),
            timeout=get_predict_settings().request_timeout_seconds,
        )
    except asyncio.TimeoutError:
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason="timeout",
        )
        log.error("predict.timeout", request_id=request_id, input_digest=input_hash, duration_ms=_duration_ms())
        return _problem(
            503, "timeout", "Prediction timed out",
            "This structure could not be processed within the allotted time. This is not "
            "necessarily a problem with your input -- please try again.",
            request_id,
        )
    except StructureError as exc:
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason=str(exc),
        )
        log.info("predict.rejected", request_id=request_id, input_digest=input_hash, reason=str(exc), duration_ms=_duration_ms())
        return _problem(
            422, "invalid-structure", "Molecular structure could not be processed", str(exc), request_id,
            errors=[ErrorDetail(field="structure.value", code="invalid_structure", message=str(exc))],
        )
    except ReproducibilityError as exc:
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason=f"reproducibility_violation: {exc}",
        )
        log.error(
            "predict.reproducibility_violation", request_id=request_id, expected=exc.expected, actual=exc.actual,
            duration_ms=_duration_ms(),
        )
        return _problem(
            500, "internal-error", "Prediction could not be produced safely",
            "The serving environment's feature computation does not match the validated model's training "
            "environment. This is a service configuration problem, not an issue with your input.",
            request_id,
        )
    except UnknownEndpointError as exc:
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason=f"unknown_endpoint: {body.endpoint}",
        )
        log.info("predict.unknown_endpoint", request_id=request_id, endpoint=body.endpoint, duration_ms=_duration_ms())
        return _problem(
            404, "unknown-endpoint", "Unknown endpoint",
            f"{exc.message} See GET /endpoints for the list of registered endpoints.",
            request_id,
            errors=[ErrorDetail(field="endpoint", code="unknown_endpoint", message=exc.message)],
        )
    except EndpointNotAvailableError as exc:
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason=f"endpoint_not_available: {exc.model_id} ({exc.final_report_status})",
        )
        log.info(
            "predict.endpoint_not_available", request_id=request_id, endpoint=exc.model_id,
            final_report_status=exc.final_report_status, duration_ms=_duration_ms(),
        )
        return _problem(
            403, "endpoint-not-available", "Endpoint not available for predictions",
            (
                f"Endpoint {exc.model_id!r} is registered with status {exc.final_report_status!r}, which has not "
                "passed the promotion gate for normal predictions. See GET /endpoints for which endpoints are servable."
            ),
            request_id,
            errors=[ErrorDetail(field="endpoint", code="endpoint_not_available", message=exc.message)],
        )
    except Exception as exc:  # noqa: BLE001 -- last-resort safety net, deliberately broad.
        # Phase 7 audit finding: without this, an IntegrityError (a checksum
        # mismatch surfacing mid-request, e.g. from get_model_bundle()) or
        # any other unhandled exception (a bug in feature computation, an
        # OS-level I/O error) would previously propagate past this handler
        # entirely -- skipping store.record_rejection (breaking "every
        # prediction must be logged", this module's own stated invariant)
        # and reaching Starlette's default handler as a raw, unformatted
        # response. It would also print a raw traceback to stderr outside
        # the structlog/redaction chain: an arbitrary exception's message is
        # not guaranteed to satisfy StructureError's "never embed the raw
        # structure" contract (RDKit's own exception text sometimes does),
        # so logging only the exception *type* here -- never str(exc) -- is
        # deliberate, not an oversight.
        store.record_rejection(
            prediction_id=prediction_id, request_id=request_id, created_at=created_at,
            input_hash=input_hash, rejection_reason=f"unexpected_error: {type(exc).__name__}",
        )
        log.error(
            "predict.unexpected_error", request_id=request_id, input_digest=input_hash,
            error_type=type(exc).__name__, duration_ms=_duration_ms(),
        )
        return _problem(
            500, "internal-error", "Prediction could not be completed",
            "An unexpected error occurred while processing this request. This has been logged for "
            "investigation and is not the result of anything wrong with your input.",
            request_id,
        )

    canonical_hash = structure_digest(result.canonical_smiles)
    response = _result_to_response(prediction_id, request_id, result, input_hash)
    store.record_success(
        prediction_id=prediction_id, request_id=request_id, created_at=created_at,
        model_id=result.model_id, model_version=result.model_version, dataset_version=result.dataset_version,
        feature_set_id=result.feature_set_id, input_hash=input_hash, canonical_structure_hash=canonical_hash,
        applicability_domain_verdict=result.applicability_domain.verdict,
        predicted_label=result.predicted_label, predicted_probability_blocker=result.predicted_probability_blocker,
        response_json=response.model_dump_json(),
        api_key_hash=getattr(request.state, "api_key_hash", None),
    )
    log.info(
        "predict.complete", request_id=request_id, prediction_id=prediction_id,
        canonical_digest=canonical_hash, applicability_domain=result.applicability_domain.verdict,
        predicted_label=result.predicted_label, duration_ms=_duration_ms(),
    )
    return JSONResponse(status_code=200, content=response.model_dump())


@app.post("/v1/psychiatric-screening", response_model=PsychiatricScreeningResponse, status_code=200)
async def psychiatric_screening(body: PsychiatricScreeningRequest, request: Request) -> JSONResponse:
    """Run the psychiatric compound screening research pipeline on one structure.

    A separate, explicitly-labelled surface from `/predict` -- see
    `drugsim_predict.psychiatric_pipeline`'s module docstring for why.
    Combines six signals (DRD2, HRH1, a DRD2/HRH1 selectivity index,
    CYP2D6, BBB, and the existing validated hERG model) into one
    response; every signal carries its own honest `reliability_tier`
    (`"validated"` for hERG only, `"experimental"` for the rest -- none
    of the four experimental endpoints has independent external
    validation). This is a non-clinical research tool: no output here is
    a diagnosis, a treatment recommendation, or a substitute for
    pharmacological or clinical judgment.

    Not persisted to the prediction-history store `GET /predict/{id}`
    serves -- this endpoint has no audit-log/history surface of its own
    yet. Subject to the same API key, rate-limit, concurrency, and body-
    size middleware as every other route (applied globally, not per-route).
    """
    request_id = request.state.request_id
    start_time = time.monotonic()

    def _duration_ms() -> float:
        return round((time.monotonic() - start_time) * 1000, 1)

    log.info("psychiatric_screening.request", request_id=request_id, input_digest=structure_digest(body.smiles))

    try:
        response = await asyncio.wait_for(
            run_in_threadpool(run_psychiatric_screening, body.smiles),
            timeout=get_predict_settings().request_timeout_seconds,
        )
    except asyncio.TimeoutError:
        log.error("psychiatric_screening.timeout", request_id=request_id, duration_ms=_duration_ms())
        return _problem(
            503, "timeout", "Screening timed out",
            "This structure could not be processed within the allotted time. This is not "
            "necessarily a problem with your input -- please try again.",
            request_id,
        )
    except StructureError as exc:
        log.info("psychiatric_screening.rejected", request_id=request_id, reason=str(exc), duration_ms=_duration_ms())
        return _problem(
            422, "invalid-structure", "Molecular structure could not be processed", str(exc), request_id,
            errors=[ErrorDetail(field="smiles", code="invalid_structure", message=str(exc))],
        )
    except Exception as exc:  # noqa: BLE001 -- last-resort safety net, same rationale as /predict's.
        log.error(
            "psychiatric_screening.unexpected_error", request_id=request_id,
            error_type=type(exc).__name__, duration_ms=_duration_ms(),
        )
        return _problem(
            500, "internal-error", "Screening could not be completed",
            "An unexpected error occurred while processing this request. This has been logged for "
            "investigation and is not the result of anything wrong with your input.",
            request_id,
        )

    log.info("psychiatric_screening.complete", request_id=request_id, duration_ms=_duration_ms())
    return JSONResponse(status_code=200, content=response.model_dump())


@app.get("/predict/{prediction_id}", response_model=PredictionResponse)
def get_prediction(prediction_id: str, request: Request, store: PredictionStore = Depends(get_store)) -> JSONResponse:
    """Retrieve a previously computed prediction envelope by its ID.

    Confidentiality audit finding (2026-08-22): this handler previously
    returned any prediction to any caller holding any one configured API
    key, regardless of who created it -- there was no ownership check at
    all. IDs are high-entropy ULIDs (not practically guessable), but that
    is not defense in depth: if an ID were ever exposed through any other
    channel (a shared JSON export, a support ticket, a copied URL), anyone
    holding a valid key could then fetch that caller's canonical structure.

    Now scoped to the API key that created it, whenever key auth is
    configured: :class:`~drugsim_predict.security.ApiKeyMiddleware` hashes
    the validated key onto ``request.state.api_key_hash``, and a row only
    matches if its own stored ``api_key_hash`` (see store.py) is identical.
    A mismatch returns the SAME 404 as a genuinely unknown ID -- never 403
    -- so this endpoint cannot be used to confirm which IDs exist for
    someone who does not already have access to them (TDS Sec 5.3's
    non-disclosing-response principle, applied here for the first time).
    When no API key is configured at all (local/dev), this check is
    skipped, matching every other route's permissive-when-unconfigured
    behaviour.
    """
    request_id = request.state.request_id
    row = store.get(prediction_id)
    settings = get_predict_settings()
    if row is None or row["response_json"] is None:
        return _problem(404, "not-found", "Prediction not found", f"No completed prediction with id {prediction_id!r}", request_id)
    if settings.api_key_set and row.get("api_key_hash") != getattr(request.state, "api_key_hash", None):
        return _problem(404, "not-found", "Prediction not found", f"No completed prediction with id {prediction_id!r}", request_id)
    return JSONResponse(status_code=200, content=PredictionResponse.model_validate_json(row["response_json"]).model_dump())
