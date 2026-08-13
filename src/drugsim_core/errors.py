"""Exception hierarchy.

Every DrugSim exception carries a stable ``code`` used for the RFC 9457 ``type``
slug in API responses (TDS §5.3), so that error identity is decoupled from message
wording and can be relied upon by clients.

Exceptions carry structured ``context`` rather than interpolating detail into the
message. Interpolation is the most common way a molecular structure reaches a log
line, because exception text is formatted and logged by handlers far from the raise
site. Structured context passes through the redaction processor; a formatted string
may not (TDS §7.2.3).
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "ConfigurationError",
    "DrugSimError",
    "EndpointNotAvailableError",
    "IntegrityError",
    "LicenseViolationError",
    "ProvenanceError",
    "ReproducibilityError",
    "StructureError",
    "UnknownEndpointError",
    "ValidationGateError",
]


class DrugSimError(Exception):
    """Base class for all DrugSim errors.

    Attributes:
        code: Stable machine-readable identifier.
        context: Structured detail, scrubbed by the logging redaction processor.
    """

    code: str = "internal_error"
    http_status: int = 500

    def __init__(self, message: str, **context: Any) -> None:
        """Initialise the error.

        Args:
            message: Human-readable description. Must not contain a molecular
                structure — pass structures via ``context`` instead.
            **context: Structured detail attached to the error.
        """
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = context

    def to_dict(self) -> dict[str, Any]:
        """Return a serialisable representation.

        Returns:
            A mapping with ``code``, ``message`` and ``context``.
        """
        return {"code": self.code, "message": self.message, "context": self.context}


class ConfigurationError(DrugSimError):
    """Configuration is missing, malformed, or unsafe for the environment."""

    code = "configuration_error"


class StructureError(DrugSimError):
    """A molecular structure could not be parsed, sanitised, or standardised.

    Maps to HTTP 422 with the underlying toolkit message, because a chemist can act
    on "explicit valence for atom 3 N is 4" but not on "invalid input" (TDS §5.3).
    """

    code = "invalid_structure"
    http_status = 422


class ValidationGateError(DrugSimError):
    """A pipeline validation gate rejected a batch.

    Gates are hard stops. This exception halts the pipeline and quarantines the
    batch; it is never caught and downgraded to a warning, because warn-and-continue
    is how bad data reaches models (Phase 1 Step 2 §4).
    """

    code = "validation_gate_failed"

    def __init__(self, gate: str, message: str, **context: Any) -> None:
        """Initialise the error.

        Args:
            gate: Gate identifier, e.g. ``"G4"``.
            message: Description of the failure.
            **context: Structured detail.
        """
        super().__init__(message, gate=gate, **context)
        self.gate = gate


class LicenseViolationError(DrugSimError):
    """An operation would breach dataset licensing.

    Raised when black-tier data would reach a commercial artefact, when a record
    lacks a licence tag, or when an upstream licence has changed since the last
    snapshot (rules LC-01 … LC-06).
    """

    code = "license_violation"


class ProvenanceError(DrugSimError):
    """A record is missing required provenance.

    Provenance is per-record, not per-dataset, because BindingDB is internally
    split-licensed (ADR-007). A record without ``source_id``, ``source_version`` and
    ``source_license`` cannot be published.
    """

    code = "provenance_missing"


class ReproducibilityError(DrugSimError):
    """An operation would break the reproducibility contract.

    The canonical case is a mismatch between a model's training ``feature_set_id``
    and the one presented at inference. This must raise rather than warn: a warning
    here means silently wrong predictions at scale (TDS §6.6, risk R5).
    """

    code = "reproducibility_violation"

    def __init__(
        self,
        message: str,
        expected: Optional[str] = None,
        actual: Optional[str] = None,
        **context: Any,
    ) -> None:
        """Initialise the error.

        Args:
            message: Description of the violation.
            expected: The expected identifier.
            actual: The identifier actually presented.
            **context: Structured detail.
        """
        super().__init__(message, expected=expected, actual=actual, **context)
        self.expected = expected
        self.actual = actual


class IntegrityError(DrugSimError):
    """A database or data-integrity invariant was violated."""

    code = "integrity_violation"


class UnknownEndpointError(DrugSimError):
    """A request named a ``model_id``/endpoint that has no registry entry at all.

    Distinct from :class:`EndpointNotAvailableError`: this is "no such
    endpoint exists," not "it exists but isn't promoted for serving."
    """

    code = "unknown_endpoint"
    http_status = 404


class EndpointNotAvailableError(DrugSimError):
    """A request named a real, registered endpoint that has not passed the
    promotion gate (Phase 9 Sec 14) and therefore cannot serve normal
    predictions.

    ``REJECTED`` and ``EXPERIMENTAL`` models may still exist in the
    registry (for internal record-keeping and research use, per the same
    section) — they must simply never be reachable through the normal
    prediction path. Raised, never silently downgraded to a warning, for
    the same reason a checksum mismatch is a hard failure: serving an
    unvalidated model as if it were validated is a scientific integrity
    violation, not a recoverable inconvenience.
    """

    code = "endpoint_not_available"
    http_status = 403

    def __init__(self, message: str, *, model_id: str, final_report_status: str, **context: Any) -> None:
        super().__init__(message, model_id=model_id, final_report_status=final_report_status, **context)
        self.model_id = model_id
        self.final_report_status = final_report_status
