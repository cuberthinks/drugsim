"""Configuration for the prediction engine.

Follows the same layered-settings convention as :mod:`drugsim_core.config`
(env vars win over defaults), scoped to this package's own concerns rather
than extending the shared ``Settings`` class — the inference service's
paths (model registry, prediction log) are not something the rest of the
platform needs to know about.

Phase 8 addition: ``environment`` reuses :class:`drugsim_core.config.Environment`
(the platform-wide ``DRUGSIM_ENVIRONMENT`` variable) rather than inventing a
second, service-local notion of environment — everything else here stays
``DRUGSIM_PREDICT_``-scoped, since it genuinely is this service's own
concern (model paths, request limits, API keys for this service only).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from drugsim_core.config import Environment

__all__ = ["PredictSettings", "get_predict_settings"]


def _project_root() -> Path:
    """Repository root, derived from this file's location."""
    return Path(__file__).resolve().parents[2]


class PredictSettings(BaseSettings):
    """Paths and limits for the prediction engine.

    All fields are overridable via ``DRUGSIM_PREDICT_*`` environment
    variables for deployment flexibility, defaulting to the checked-in
    locations for local/test use. ``environment`` is the one exception,
    reading the shared ``DRUGSIM_ENVIRONMENT`` variable.
    """

    model_config = SettingsConfigDict(env_prefix="DRUGSIM_PREDICT_", extra="ignore")

    registry_path: Path = Path(__file__).resolve().parents[2] / "models" / "registry" / "herg_inhibition_v1.json"
    # Phase 9: the directory scanned to resolve any OTHER endpoint's
    # registry file by model_id. ``registry_path`` above is kept as its own
    # field (rather than derived from this) so existing overrides of it
    # (env var or direct construction, e.g. in tests) keep pointing hERG at
    # exactly the file they always did -- this is purely additive.
    registry_dir: Path = Path(__file__).resolve().parents[2] / "models" / "registry"
    prediction_db_path: Path = _project_root() / "var" / "predictions.sqlite3"
    # Offline-built, committed snapshot (see scripts/build_compound_identity_
    # snapshot.py) -- the live service only ever reads this file, never
    # PubChem directly, preserving the "no third party receives a submitted
    # structure" guarantee (docs/privacy/confidentiality-audit.md Sec 8).
    compound_identity_snapshot_path: Path = (
        Path(__file__).resolve().parents[2] / "src" / "drugsim_identity" / "data" / "compound_identity_snapshot.json"
    )
    max_smiles_length: int = 5000
    max_molecular_weight: float = 2000.0
    request_timeout_seconds: float = 10.0

    environment: Environment = Environment.LOCAL

    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Comma-separated API keys. Empty means "no auth configured" -- allowed
    # in local/dev/test (nothing to protect there), refused at startup in
    # staging/production (see api_keys validator and api.py's startup
    # check) so a deployment can never silently go live unauthenticated.
    # Never logged: this field itself is only ever read for membership
    # checks, never included in a log event.
    api_keys: str = ""

    max_request_body_bytes: int = 65_536  # 64 KiB -- generous over the 6,000-char structure ceiling.
    rate_limit_requests_per_minute: int = 30
    max_concurrent_requests: int = 10

    @field_validator("environment", mode="before")
    @classmethod
    def _read_shared_environment_var(cls, value: object) -> object:
        """Fall back to ``DRUGSIM_ENVIRONMENT`` (the platform-wide variable)
        when ``DRUGSIM_PREDICT_ENVIRONMENT`` is not set, so this service
        does not require a second, duplicate environment variable in every
        deployment's configuration."""
        import os

        if value is not None:
            return value
        return os.environ.get("DRUGSIM_ENVIRONMENT", Environment.LOCAL.value)

    @property
    def api_key_set(self) -> frozenset[str]:
        """Configured API keys as a set, ignoring blank entries."""
        return frozenset(k.strip() for k in self.api_keys.split(",") if k.strip())

    @property
    def cors_origins(self) -> list[str]:
        """Configured CORS origins as a list, ignoring blank entries."""
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_predict_settings() -> PredictSettings:
    """Return the process-wide settings singleton."""
    return PredictSettings()


def assert_safe_to_start(settings: Optional[PredictSettings] = None) -> None:
    """Refuse to start in an unsafe configuration.

    Fail-safe, not fail-open (TDS's own pattern, reused here): a staging or
    production deployment with no API keys configured would otherwise start
    successfully and serve every endpoint to the open internet
    unauthenticated. Raising here means that misconfiguration is a startup
    crash, not a silent security gap.

    Raises:
        RuntimeError: If ``environment.is_production_like`` and no API key
            is configured.
    """
    settings = settings or get_predict_settings()
    if settings.environment.is_production_like and not settings.api_key_set:
        msg = (
            f"DRUGSIM_PREDICT_API_KEYS is not set, but DRUGSIM_ENVIRONMENT="
            f"'{settings.environment.value}' is production-like. Refusing to start "
            "an unauthenticated deployment. Set at least one API key, or run with "
            "DRUGSIM_ENVIRONMENT=local/development/test if this is intentional."
        )
        raise RuntimeError(msg)
