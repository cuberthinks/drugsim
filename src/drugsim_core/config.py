"""Layered configuration management.

Configuration resolves in precedence order (later wins):

1. Field defaults declared here
2. ``config/base.yaml``
3. ``config/environments/{environment}.yaml``
4. Environment variables prefixed ``DRUGSIM_``
5. Explicit constructor arguments

Secrets are **never** read from YAML. Any field holding a credential is populated
from the environment only, which in production is injected from the secret manager
(TDS §7.6). ``config/`` holds non-secret defaults and is committed; a secret found
in a YAML file is a defect, and :meth:`Settings.assert_no_secrets_in_yaml` fails
loudly if one appears.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Environment", "Settings", "get_settings", "load_yaml_config"]

_ENV_PREFIX = "DRUGSIM_"

#: Field names that must only ever come from the environment, never from YAML.
_SECRET_FIELDS = frozenset(
    {
        "database_password",
        "object_storage_secret_key",
        "object_storage_access_key",
    }
)


class Environment(str, Enum):
    """Deployment environment (TDS §10.1)."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        """Whether this environment holds real customer data."""
        return self in (Environment.STAGING, Environment.PRODUCTION)


def _project_root() -> Path:
    """Return the repository root, derived from this file's location."""
    return Path(__file__).resolve().parents[2]


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Load a YAML configuration file.

    Args:
        path: Path to the file. A missing file yields an empty mapping, so that
            optional per-environment overlays need not exist.

    Returns:
        The parsed mapping.

    Raises:
        ValueError: If the file exists but does not contain a mapping.
    """
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        msg = f"configuration file {path} must contain a mapping, got {type(data).__name__}"
        raise ValueError(msg)
    return data


class Settings(BaseSettings):
    """Application settings.

    Attributes are grouped by concern. Every field carries a default suitable for
    local development; production values arrive from the environment.
    """

    model_config = SettingsConfigDict(
        env_prefix=_ENV_PREFIX,
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="forbid",
        validate_default=True,
    )

    # -- Environment ------------------------------------------------------
    environment: Environment = Field(
        default=Environment.LOCAL,
        description="Deployment environment.",
    )
    debug: bool = Field(default=False, description="Verbose diagnostics. Never true in production.")

    # -- Logging ----------------------------------------------------------
    log_level: str = Field(default="INFO", description="Root log level.")
    log_format: str = Field(default="json", description="Log renderer: 'json' or 'console'.")

    # -- Database ---------------------------------------------------------
    database_host: str = Field(default="localhost")
    database_port: int = Field(default=5432, ge=1, le=65535)
    database_name: str = Field(default="drugsim")
    database_user: str = Field(default="drugsim")
    database_password: SecretStr = Field(default=SecretStr("drugsim_local_dev"))
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_statement_timeout_ms: int = Field(
        default=30_000,
        ge=1000,
        description="Server-side statement timeout. Bounds runaway substructure queries.",
    )

    # -- Object storage (data lake) ---------------------------------------
    object_storage_endpoint: str = Field(default="http://localhost:9000")
    object_storage_access_key: SecretStr = Field(default=SecretStr("minioadmin"))
    object_storage_secret_key: SecretStr = Field(default=SecretStr("minioadmin"))
    object_storage_region: str = Field(default="us-east-1")
    bucket_landing: str = Field(default="drugsim-z1-landing")
    bucket_conformed: str = Field(default="drugsim-z2-conformed")
    bucket_curated: str = Field(default="drugsim-z3-curated")
    bucket_features: str = Field(default="drugsim-features")
    bucket_artifacts: str = Field(default="drugsim-artifacts")

    # -- Paths ------------------------------------------------------------
    config_dir: Path = Field(default_factory=lambda: _project_root() / "config")
    registry_path: Path = Field(default_factory=lambda: _project_root() / "datasets" / "registry.yaml")
    golden_dir: Path = Field(default_factory=lambda: _project_root() / "datasets" / "golden")

    # -- Pipeline ---------------------------------------------------------
    download_max_retries: int = Field(default=5, ge=1, le=20)
    download_timeout_seconds: int = Field(default=1800, ge=30)
    download_chunk_bytes: int = Field(default=8 * 1024 * 1024, ge=8192)

    # -- Safety limits (TDS §7.7) -----------------------------------------
    max_upload_bytes: int = Field(default=100 * 1024 * 1024)
    max_records_per_upload: int = Field(default=10_000)
    max_record_bytes: int = Field(default=100 * 1024)
    structure_parse_timeout_seconds: int = Field(default=5, ge=1, le=60)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        """Normalise and validate the log level."""
        upper = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if upper not in allowed:
            msg = f"log_level must be one of {sorted(allowed)}, got {value!r}"
            raise ValueError(msg)
        return upper

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        """Validate the log renderer selection."""
        lower = value.lower()
        if lower not in {"json", "console"}:
            msg = f"log_format must be 'json' or 'console', got {value!r}"
            raise ValueError(msg)
        return lower

    @model_validator(mode="after")
    def _validate_production_invariants(self) -> Settings:
        """Reject configurations that are unsafe in production-like environments.

        Debug mode and console logging are development conveniences. Debug output can
        include payloads, which is the exact path by which a customer structure would
        reach a log (TDS §7.2.3).

        Raises:
            ValueError: If a production-like environment has unsafe settings.
        """
        if self.environment.is_production_like:
            if self.debug:
                msg = f"debug must be false in {self.environment.value}"
                raise ValueError(msg)
            if self.log_format != "json":
                msg = f"log_format must be 'json' in {self.environment.value}"
                raise ValueError(msg)
        return self

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy connection URL with the password revealed.

        Returns:
            A ``postgresql+psycopg://`` URL. Never log this value.
        """
        password = self.database_password.get_secret_value()
        return (
            f"postgresql+psycopg://{self.database_user}:{password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @staticmethod
    def assert_no_secrets_in_yaml(config_dir: Path) -> None:
        """Verify that no secret-bearing field appears in committed YAML.

        Called at startup and asserted in CI. A secret in a committed file is a
        disclosure the moment the repository is cloned, and rotation is the only
        remedy — so this fails loudly rather than warning.

        Args:
            config_dir: Directory containing YAML configuration.

        Raises:
            ValueError: If a secret field name is present in any YAML file.
        """
        offenders: list[str] = []
        for path in sorted(config_dir.rglob("*.yaml")):
            data = load_yaml_config(path)
            offenders.extend(
                f"{path.name}:{key}" for key in data if key.lower() in _SECRET_FIELDS
            )
        if offenders:
            msg = (
                "secret-bearing fields found in committed configuration: "
                f"{', '.join(offenders)}. Secrets must come from the environment only."
            )
            raise ValueError(msg)


def _resolve_environment() -> Environment:
    """Determine the active environment from the process environment."""
    raw = os.environ.get(f"{_ENV_PREFIX}ENVIRONMENT", Environment.LOCAL.value)
    try:
        return Environment(raw.lower())
    except ValueError as exc:
        valid = [e.value for e in Environment]
        msg = f"unknown environment {raw!r}; expected one of {valid}"
        raise ValueError(msg) from exc


def build_settings(config_dir: Optional[Path] = None, **overrides: Any) -> Settings:
    """Build settings from the YAML layers, environment, and explicit overrides.

    Args:
        config_dir: Directory containing ``base.yaml`` and ``environments/``.
            Defaults to ``<project root>/config``.
        **overrides: Explicit values taking highest precedence.

    Returns:
        A validated :class:`Settings` instance.
    """
    environment = _resolve_environment()
    directory = config_dir if config_dir is not None else _project_root() / "config"

    merged: dict[str, Any] = {}
    merged.update(load_yaml_config(directory / "base.yaml"))
    merged.update(load_yaml_config(directory / "environments" / f"{environment.value}.yaml"))
    merged.pop("environment", None)  # environment is authoritative from the env var

    # Drop any YAML key that is also set in the environment.
    #
    # pydantic-settings ranks constructor arguments ABOVE environment variables. YAML
    # values are passed as constructor arguments, so without this filter a committed
    # YAML default would silently override an operator's environment variable —
    # inverting the documented precedence and making production overrides ineffective.
    # Removing shadowed keys restores: overrides > env > environment YAML > base YAML.
    env_keys = {
        key[len(_ENV_PREFIX) :].lower()
        for key in os.environ
        if key.startswith(_ENV_PREFIX)
    }
    merged = {key: value for key, value in merged.items() if key.lower() not in env_keys}

    # Explicit overrides outrank everything, including the environment.
    merged.update(overrides)

    return Settings(environment=environment, **merged)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that configuration is resolved once and cannot drift mid-process.
    Tests that need different settings should call :func:`build_settings` directly
    or clear the cache via ``get_settings.cache_clear()``.

    Returns:
        The validated settings.
    """
    return build_settings()
