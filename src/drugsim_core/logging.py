"""Structured logging configuration.

Emits structured JSON to stdout in deployed environments and human-readable output
locally (TDS §3.10). Every record carries the fields needed to correlate a log line
with a request, a trace, and — where relevant — a prediction.

Architecture: structlog and the standard library share a single processor chain via
``ProcessorFormatter``. Third-party libraries (SQLAlchemy, botocore, httpx) log
through stdlib, and routing both through one chain means there is exactly one place
where redaction happens and no path that bypasses it.

:func:`drugsim_core.redaction.redact_event` is placed **last before rendering**, so
it sees the fully assembled event including formatted exception text — a common leak
path, because exception messages are formatted and logged by handlers far from the
raise site. A redaction step placed earlier would be bypassed by any processor that
adds data after it.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional

import structlog
from structlog.types import Processor

from drugsim_core.redaction import redact_event
from drugsim_core.version import get_version

__all__ = [
    "bind_request_context",
    "clear_context",
    "configure_logging",
    "get_logger",
    "reset_logging",
]

_configured = False


def _drop_color_message_key(
    _logger: Any,  # noqa: ANN401
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Remove uvicorn's duplicate ``color_message`` key if present."""
    event_dict.pop("color_message", None)
    return event_dict


def _shared_processors() -> list[Processor]:
    """Return processors applied to both structlog and stdlib records."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _drop_color_message_key,
    ]


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    service_name: str = "drugsim",
) -> None:
    """Configure structlog and the stdlib logging bridge.

    Idempotent: repeated calls have no additional effect, so importing modules that
    configure logging cannot produce duplicated processor chains.

    Args:
        level: Root log level name.
        fmt: ``"json"`` for machine-readable output, ``"console"`` for local use.
        service_name: Value bound to every record as ``service``.
    """
    global _configured  # noqa: PLW0603
    if _configured:
        return

    shared = _shared_processors()
    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        # Caching is disabled so that reconfiguration takes effect immediately.
        # Cached bound loggers retain the previous chain, which makes redaction
        # behaviour depend on import order — unacceptable for a security control.
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            # LAST before rendering — see module docstring.
            redact_event,
            renderer,
        ],
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    for noisy in ("urllib3", "botocore", "boto3", "s3transfer", "asyncio", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    structlog.contextvars.bind_contextvars(service=service_name, version=get_version())
    _configured = True


def reset_logging() -> None:
    """Reset all logging configuration. Intended for tests only."""
    global _configured  # noqa: PLW0603
    _configured = False
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)


def get_logger(name: Optional[str] = None) -> Any:  # noqa: ANN401
    """Return a bound structlog logger.

    Args:
        name: Logger name, conventionally ``__name__``.

    Returns:
        A bound logger.
    """
    return structlog.get_logger(name)


def bind_request_context(
    request_id: str,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Bind request-scoped identifiers to all subsequent log records.

    ``tenant_id`` is bound because every access-control decision and every audit
    entry is tenant-scoped; having it on the record is what makes a cross-tenant
    investigation tractable (TDS §7.2).

    Args:
        request_id: Correlation identifier echoed as ``X-Request-Id``.
        user_id: Authenticated user public ID, if any.
        tenant_id: Tenant public ID, if any.
    """
    context: dict[str, str] = {"request_id": request_id}
    if user_id is not None:
        context["user_id"] = user_id
    if tenant_id is not None:
        context["tenant_id"] = tenant_id
    structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear request-scoped context. Call at the end of each request."""
    structlog.contextvars.clear_contextvars()
