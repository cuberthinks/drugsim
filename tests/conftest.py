"""Shared pytest fixtures and collection rules."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from drugsim_core.config import get_settings
from drugsim_core.logging import reset_logging
from drugsim_predict.security import reset_rate_limit_state
from drugsim_predict.settings import get_predict_settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isolate each test from ambient DRUGSIM_* environment variables.

    Without this, a developer's shell configuration silently changes test outcomes,
    which is the classic source of "passes locally, fails in CI".
    """
    for key in list(os.environ):
        if key.startswith("DRUGSIM_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DRUGSIM_ENVIRONMENT", "test")
    get_settings.cache_clear()
    get_predict_settings.cache_clear()
    reset_rate_limit_state()
    yield
    get_settings.cache_clear()
    get_predict_settings.cache_clear()
    reset_rate_limit_state()


@pytest.fixture(autouse=True)
def _reset_logging_state() -> Iterator[None]:
    """Reset structlog between tests so processor chains cannot leak across them."""
    reset_logging()
    yield
    reset_logging()


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Return the repository root."""
    return Path(__file__).resolve().parents[1]
