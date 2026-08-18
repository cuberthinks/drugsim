"""Load the validated Phase 4 model with integrity verification.

Per TDS Sec 6.6 stage 2 ("Model load — resolve alias -> model_version;
verify artifact_sha256; cache in worker memory"): every artifact this
module loads (the classifier, the frozen conformal calibration scores, the
applicability-domain reference data, the descriptor scaler, and the
inference-support manifest carrying the k-NN/conformal thresholds) is
checksum-verified against the value recorded at registration time. A
mismatch is a hard failure, never a warning — a silently-swapped artifact
is a silently wrong model, and TDS Sec 6.6 stage 3 treats that class of
error as structurally unacceptable. (Phase 7 hardening: the manifest was
previously loaded without a checksum, the one artifact in the bundle that
was not — closed as part of the Phase 7 security audit.)

Nothing here recomputes anything. The calibration nonconformity scores,
training fingerprints/descriptors, scaffold set, and k-NN threshold were
all frozen by ``models/admet/herg_inhibition/10_export_inference_support.py``
at Phase 5 build time, from the exact Phase 3/4 calibration and training
splits. Recomputing any of it here would silently diverge from what was
actually validated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import structlog

from drugsim_core.errors import IntegrityError, UnknownEndpointError

from drugsim_predict.settings import get_predict_settings

__all__ = [
    "DEFAULT_MODEL_ID",
    "EndpointSummary",
    "ModelBundle",
    "get_model_bundle",
    "list_registered_endpoints",
    "load_model_bundle",
]

log = structlog.get_logger(__name__)

#: The endpoint served when a caller does not specify one -- preserves every
#: pre-Phase-9 call site's behaviour (``get_model_bundle()``,
#: ``run_inference(structure, fmt)``) exactly as it was.
DEFAULT_MODEL_ID = "herg_inhibition"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify(path: Path, expected_sha256: str, *, label: str) -> None:
    if not path.exists():
        msg = f"{label} artifact missing: {path}"
        raise IntegrityError(msg, path=str(path))
    actual = _sha256(path)
    if actual != expected_sha256:
        msg = f"{label} artifact checksum mismatch — possible corruption or an unregistered swap"
        raise IntegrityError(msg, path=str(path), expected=expected_sha256, actual=actual)


@dataclass(frozen=True)
class ModelBundle:
    """Everything the inference pipeline needs, loaded once and reused.

    Attributes:
        registry: The raw ``models/registry/*.json`` content, for endpoints
            that expose full model metadata verbatim.
        model_id: e.g. ``herg_inhibition``.
        model_version: e.g. ``0.1.0``.
        model_checksum: SHA-256 of the exact model artifact file, verified
            at load time -- surfaced on every prediction (Phase 7
            reproducibility requirement) so a prediction's metadata alone
            identifies exactly which model binary produced it.
        final_report_status: The Phase 4 classification (e.g.
            ``VALIDATED FOR INTERNAL RESEARCH``) — surfaced on every
            prediction so a caller cannot mistake this for a fully
            validated clinical tool.
        feature_set_id: ADR-005 content address. Any mismatch between this
            and a freshly computed one is a hard error (TDS Sec 6.6 stage 3).
        descriptor_fields: Exact column order the model was trained on.
        sklearn_model: The loaded, checksum-verified classifier.
        calibration_nonconformity: Frozen nonconformity scores from the
            Phase 3 calibration split (split_group 7). Never refit here.
        train_fingerprints / train_descriptors: Frozen training-set
            reference data (groups 0-6) for the applicability-domain
            Tanimoto and k-NN checks.
        train_scaffolds: Frozen training-set Bemis-Murcko scaffold set,
            for the scaffold-seen AD component.
        descriptor_ad_scaler: `StandardScaler` fit on training descriptors
            ONLY for the descriptor-space k-NN distance AD check — separate
            from the model's own input, which uses raw (unscaled)
            descriptors concatenated with the fingerprint.
        knn_distance_threshold_p95: 95th percentile of training-internal
            k-NN distances, frozen from Phase 3/4.
        positive_class_label / negative_class_label: The endpoint's own
            label vocabulary (e.g. hERG's ``"blocker"``/``"non_blocker"``,
            CYP3A4's ``"inhibitor"``/``"non_inhibitor"``) — Phase 9
            genericisation. Read from the registry's ``endpoint`` block;
            defaults to ``"blocker"``/``"non_blocker"`` when absent so
            hERG's registry file needs no edit at all to keep producing the
            exact strings it always has.
    """

    registry: dict[str, Any]
    model_id: str
    model_version: str
    model_checksum: str
    dataset_version: str
    final_report_status: str
    feature_set_id: str
    descriptor_spec_version: str
    standardization_pipeline_version: str
    rdkit_version: str
    descriptor_fields: list[str]
    algorithm: str
    training_set_size: int
    sklearn_model: Any
    calibration_nonconformity: np.ndarray
    train_fingerprints: np.ndarray
    train_descriptors: np.ndarray
    train_scaffolds: frozenset[str]
    descriptor_ad_scaler: Any
    knn_distance_threshold_p95: float
    knn_k: int
    nominal_confidence: float
    positive_class_label: str
    negative_class_label: str


@dataclass(frozen=True)
class EndpointSummary:
    """Lightweight, registry-only metadata for endpoint discovery.

    Deliberately does NOT load or checksum-verify the model artifact (that
    only happens in :func:`load_model_bundle`, on the path that actually
    serves a prediction) -- this is for listing what endpoints exist and
    their promotion status, e.g. for the frontend's available/experimental/
    unavailable distinction (Phase 9 Sec 17), without paying the cost or
    risk of loading every registered artifact just to enumerate them.
    """

    model_id: str
    model_version: str
    endpoint_name: str
    category: Optional[str]
    final_report_status: str
    dataset_version: str
    training_set_size: Optional[int]
    registry_path: Path


def _resolve_registry_path(model_id: str) -> Path:
    """Find the registry file for ``model_id``.

    ``herg_inhibition`` resolves through ``settings.registry_path`` exactly
    as before Phase 9 (so any existing override of that one field, e.g. in
    tests, keeps working unchanged). Any other ``model_id`` is resolved by
    scanning ``settings.registry_dir`` for the registry file whose own
    ``model_id`` field matches -- not by assuming a ``{model_id}_v1.json``
    naming convention, so a future re-versioned filename does not silently
    break resolution.

    Raises:
        UnknownEndpointError: No registry file has this ``model_id``.
    """
    settings = get_predict_settings()
    if model_id == DEFAULT_MODEL_ID:
        return settings.registry_path
    for path in sorted(settings.registry_dir.glob("*.json")):
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if candidate.get("model_id") == model_id:
            return path
    msg = f"No registered model found for endpoint {model_id!r}"
    raise UnknownEndpointError(msg, model_id=model_id)


def list_registered_endpoints() -> list[EndpointSummary]:
    """Enumerate every endpoint with a registry entry, regardless of
    promotion status -- callers decide what to do with EXPERIMENTAL/
    REJECTED entries (e.g. the API lists them but refuses to serve
    predictions for them; see :class:`~drugsim_core.errors.EndpointNotAvailableError`).
    """
    settings = get_predict_settings()
    summaries: list[EndpointSummary] = []
    for path in sorted(settings.registry_dir.glob("*.json")):
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        endpoint = registry.get("endpoint", {})
        summaries.append(
            EndpointSummary(
                model_id=registry["model_id"],
                model_version=registry.get("model_version", "unknown"),
                endpoint_name=endpoint.get("name", registry["model_id"]),
                category=endpoint.get("category"),
                final_report_status=registry.get("final_report_status", "UNKNOWN"),
                dataset_version=registry.get("dataset", {}).get("dataset_version", "unknown"),
                training_set_size=registry.get("dataset", {}).get("final_compound_count"),
                registry_path=path,
            )
        )
    return summaries


def load_model_bundle(registry_path: Optional[Path] = None, *, model_id: str = DEFAULT_MODEL_ID) -> ModelBundle:
    """Load and integrity-verify the full model bundle. Not cached.

    Args:
        registry_path: Override the configured registry file location
            directly (mainly for tests). Takes precedence over ``model_id``
            when both are given.
        model_id: Which endpoint's model to load, e.g. ``"herg_inhibition"``
            or ``"cyp3a4_inhibition"``. Ignored if ``registry_path`` is given.

    Returns:
        The verified bundle.

    Raises:
        UnknownEndpointError: ``model_id`` has no registry entry.
        IntegrityError: If any artifact is missing or its checksum does not
            match what was recorded at registration time.
    """
    path = registry_path or _resolve_registry_path(model_id)
    registry = json.loads(path.read_text(encoding="utf-8"))
    root = path.resolve().parents[2]  # models/registry/x.json -> repo root

    model_path = root / registry["artifact"]["path"]
    _verify(model_path, registry["artifact"]["sha256"], label="model")
    model = joblib.load(model_path)
    # Phase 7 performance finding: the trained estimator was pickled with
    # n_jobs=-1 (fan out across all cores via joblib's parallel backend).
    # That is the right setting for *training* or for scoring a large batch,
    # but this service predicts one molecule per request -- for a single
    # sample, joblib's worker-pool coordination overhead (measured: ~65% of
    # total inference time was spent in a polling time.sleep loop) dwarfs
    # the actual per-tree computation. Forcing sequential execution cut
    # measured per-request inference time from ~59ms to ~25ms with
    # bit-identical predict_proba output -- this changes execution strategy
    # only, never a prediction value, so it is not a methodology change.
    model.n_jobs = 1

    inf = registry["inference_support"]
    npz_path = root / inf["npz_path"]
    _verify(npz_path, inf["npz_sha256"], label="inference_support")
    scaler_path = root / inf["scaler_path"]
    _verify(scaler_path, inf["scaler_sha256"], label="descriptor_ad_scaler")
    manifest_path = root / inf["manifest_path"]
    _verify(manifest_path, inf["manifest_sha256"], label="inference_support_manifest")

    support = np.load(npz_path, allow_pickle=True)
    scaler = joblib.load(scaler_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    features = registry["features"]
    endpoint = registry.get("endpoint", {})
    return ModelBundle(
        registry=registry,
        model_id=registry["model_id"],
        model_version=registry["model_version"],
        model_checksum=registry["artifact"]["sha256"],
        dataset_version=registry["dataset"]["dataset_version"],
        final_report_status=registry["final_report_status"],
        feature_set_id=features["feature_set_id"],
        descriptor_spec_version=features["descriptor_spec_version"],
        standardization_pipeline_version=features["standardization_pipeline_version"],
        rdkit_version=features["rdkit_version"],
        descriptor_fields=features["descriptor_fields"],
        algorithm=registry["algorithm"],
        # The compounds actually fit on (split_groups 0-6), not the full
        # 9,589-compound dataset -- TDS's own AD-warning example ("Model
        # trained on 475 compounds") means the training split specifically.
        training_set_size=int(support["train_fingerprints"].shape[0]),
        sklearn_model=model,
        calibration_nonconformity=support["calibration_nonconformity"],
        train_fingerprints=support["train_fingerprints"],
        train_descriptors=support["train_descriptors"],
        train_scaffolds=frozenset(support["train_scaffolds"].tolist()),
        descriptor_ad_scaler=scaler,
        knn_distance_threshold_p95=manifest["knn_distance_threshold_p95"],
        knn_k=manifest["knn_k"],
        nominal_confidence=manifest["nominal_confidence"],
        # Default preserves hERG's exact pre-Phase-9 strings without
        # requiring any edit to hERG's own registry file.
        positive_class_label=endpoint.get("positive_class_label", "blocker"),
        negative_class_label=endpoint.get("negative_class_label", "non_blocker"),
    )


@lru_cache(maxsize=None)
def get_model_bundle(model_id: str = DEFAULT_MODEL_ID) -> ModelBundle:
    """Return the process-wide cached model bundle for ``model_id`` (TDS
    Sec 6.6: "cache in worker memory"). Loaded and verified once per
    process per endpoint.

    Phase 9: generalised from a no-arg, single-model ``@lru_cache(maxsize=1)``
    singleton to a ``model_id``-keyed cache (``maxsize=None`` — the number
    of distinct endpoints is small and bounded by what's registered, never
    unbounded/user-controlled). ``get_model_bundle()`` with no argument is
    unchanged: it still returns exactly the hERG bundle it always did.

    Phase 8 model change control: the successful load is logged exactly
    once per process per endpoint (this function is cached, so this fires
    on first call only for a given ``model_id``) with the full model
    identity -- this is what "deployment records which model is active"
    means in practice here: every process's log stream has a permanent,
    timestamped record of exactly which model_id/version/checksum/
    dataset_version/feature_set_id it loaded, searchable through whatever
    the deployment's log pipeline is. Detecting an *accidental* replacement
    is the checksum verification above already running unconditionally: a
    swapped artifact whose registry entry was not updated to match raises
    :class:`~drugsim_core.errors.IntegrityError` and this function never
    returns a bundle at all.
    """
    bundle = load_model_bundle(model_id=model_id)
    log.info(
        "model.loaded",
        model_id=bundle.model_id,
        model_version=bundle.model_version,
        model_checksum=bundle.model_checksum,
        dataset_version=bundle.dataset_version,
        feature_set_id=bundle.feature_set_id,
        final_report_status=bundle.final_report_status,
    )
    return bundle
