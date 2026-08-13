"""Version and toolchain identification.

Reproducibility in DrugSim depends on seven independently versioned axes (Phase 1
Step 2 §7.1). This module owns two of them: the application version and the
``toolchain_id``.

``toolchain_id`` is the single most important string in the reproducibility chain.
RDKit descriptor values change between releases — bug fixes to TPSA, logP
contributions and aromaticity perception mean features computed under one version
are not interchangeable with another. The toolchain identifier is therefore an input
to ``feature_set_id`` (ADR-005), and a model trained under one toolchain must never
consume features computed under a different one.
"""

from __future__ import annotations

import hashlib
import platform
from functools import lru_cache
from typing import Optional

__all__ = ["build_toolchain_id", "get_rdkit_version", "get_toolchain_id", "get_version"]

#: Application version. Kept in sync with pyproject.toml by release tooling.
__version__ = "0.1.0"


def get_version() -> str:
    """Return the application version.

    Returns:
        A semantic version string.
    """
    return __version__


@lru_cache(maxsize=1)
def get_rdkit_version() -> Optional[str]:
    """Return the installed RDKit version, if RDKit is available.

    Returns:
        The RDKit version string, or ``None`` when RDKit is not installed.
        ``None`` is a legitimate state during Sprint 2.1, where no chemistry
        code exists yet; it becomes a hard error once descriptor computation
        is introduced.
    """
    try:
        import rdkit  # noqa: PLC0415
    except ImportError:
        return None
    version: str = rdkit.__version__
    return version


def build_toolchain_id(
    rdkit_version: Optional[str] = None,
    python_version: Optional[str] = None,
    standardization_pipeline_version: str = "unset",
) -> str:
    """Build a deterministic toolchain identifier.

    The identifier is human-readable rather than a bare hash, because it appears in
    provenance output that scientists read. Its components are exactly those that can
    change a computed descriptor value.

    Args:
        rdkit_version: RDKit version. Detected if omitted.
        python_version: Python version. Detected if omitted.
        standardization_pipeline_version: Version of the standardisation pipeline
            defined in ``drugsim_chem``. ``"unset"`` until Sprint 2.5 introduces it.

    Returns:
        An identifier of the form
        ``rdkit-2025.3.3__python-3.12.4__stdpipe-v1``.

    Raises:
        RuntimeError: If ``standardization_pipeline_version`` is ``"unset"`` while
            RDKit is installed, which would mean chemistry code is present but
            unversioned.
    """
    resolved_rdkit = rdkit_version if rdkit_version is not None else get_rdkit_version()
    resolved_python = (
        python_version if python_version is not None else platform.python_version()
    )

    if resolved_rdkit is not None and standardization_pipeline_version == "unset":
        msg = (
            "RDKit is installed but standardization_pipeline_version is 'unset'. "
            "Chemistry code must be versioned before descriptors are computed "
            "(ADR-005)."
        )
        raise RuntimeError(msg)

    rdkit_part = resolved_rdkit if resolved_rdkit is not None else "absent"
    return (
        f"rdkit-{rdkit_part}"
        f"__python-{resolved_python}"
        f"__stdpipe-{standardization_pipeline_version}"
    )


def get_toolchain_id(standardization_pipeline_version: str = "unset") -> str:
    """Return the toolchain identifier for the current process.

    Args:
        standardization_pipeline_version: Standardisation pipeline version.

    Returns:
        The toolchain identifier.
    """
    return build_toolchain_id(
        standardization_pipeline_version=standardization_pipeline_version
    )


def toolchain_digest(toolchain_id: str) -> str:
    """Return a short digest of a toolchain identifier.

    Used where a fixed-width token is needed, such as in object-storage prefixes.

    Args:
        toolchain_id: The identifier to digest.

    Returns:
        The first 12 hex characters of its SHA-256 digest.
    """
    return hashlib.sha256(toolchain_id.encode("utf-8")).hexdigest()[:12]
