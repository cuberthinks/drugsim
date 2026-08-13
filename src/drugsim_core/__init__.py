"""DrugSim core: configuration, logging, identifiers, errors, versioning.

Cross-cutting infrastructure with no scientific content. Every other DrugSim
package depends on this one; this package depends on none of them.

Modules:
    config: Layered configuration with production safety invariants.
    errors: Exception hierarchy with stable error codes.
    ids: ULID generation and prefixed public identifiers.
    logging: Structured logging with mandatory structure redaction.
    redaction: Protection of customer structures from log disclosure.
    version: Application version and the reproducibility-critical toolchain_id.
"""

from __future__ import annotations

from drugsim_core.errors import (
    ConfigurationError,
    DrugSimError,
    IntegrityError,
    LicenseViolationError,
    ProvenanceError,
    ReproducibilityError,
    StructureError,
    ValidationGateError,
)
from drugsim_core.ids import generate_ulid, parse_public_id, public_id
from drugsim_core.redaction import SensitiveStructure
from drugsim_core.version import __version__, get_toolchain_id, get_version

__all__ = [
    "ConfigurationError",
    "DrugSimError",
    "IntegrityError",
    "LicenseViolationError",
    "ProvenanceError",
    "ReproducibilityError",
    "SensitiveStructure",
    "StructureError",
    "ValidationGateError",
    "__version__",
    "generate_ulid",
    "get_toolchain_id",
    "get_version",
    "parse_public_id",
    "public_id",
]
