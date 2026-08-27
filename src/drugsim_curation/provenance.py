"""Per-record licence resolution, failing closed.

``src/drugsim_quality/license_audit.py`` already audits the *registry*
(``datasets/registry.yaml``) as a required CI gate — it answers "is this
source's licence entry well-formed and consistent?". This module answers a
different, per-record question: "for this specific curated measurement,
what licence applies, and is that licence resolved enough to use?" It
reuses ``license_audit.load_registry`` rather than re-parsing the YAML.

**Fails closed.** A source missing from the registry, or missing a
``commercial_ok`` field, is never treated as permitted by default — it is
recorded as ``unresolved`` and excluded from anything license-sensitive
until a human resolves it in the registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from drugsim_quality.license_audit import load_registry

__all__ = ["LicenseResolution", "SourceRegistry", "resolve_license"]

LicenseStatus = Literal["resolved", "unresolved"]


@dataclass(frozen=True)
class LicenseResolution:
    """The licence outcome for one record's source.

    Attributes:
        source_id: The registry source identifier looked up.
        spdx: The licence's SPDX identifier, or ``None`` if unresolved.
        tier: The licence tier (``green``/``amber``/``red``/``black``), or
            ``None`` if unresolved.
        commercial_ok: Whether commercial use is permitted, or ``None`` if
            unresolved -- never assumed ``True`` by default.
        attribution: The required attribution string, or ``None``.
        license_status: ``"resolved"`` only when the source was found in
            the registry with an explicit, well-formed licence block.
        reason: Populated only when ``license_status == "unresolved"``.
    """

    source_id: str
    spdx: Optional[str]
    tier: Optional[str]
    commercial_ok: Optional[bool]
    attribution: Optional[str]
    license_status: LicenseStatus
    reason: Optional[str] = None


class SourceRegistry:
    """A loaded ``registry.yaml``, indexed by ``source_id`` for repeated lookups.

    Loading and indexing once per curation run (rather than per record) is
    a plain performance concern, not a correctness one — the underlying
    data is identical either way.
    """

    def __init__(self, registry_data: dict[str, Any]) -> None:
        self._by_id: dict[str, dict[str, Any]] = {
            entry["source_id"]: entry for entry in registry_data.get("sources", []) if "source_id" in entry
        }

    @classmethod
    def load(cls, registry_path: Any) -> "SourceRegistry":
        """Load and index ``registry.yaml`` from ``registry_path``."""
        return cls(load_registry(registry_path))

    def get(self, source_id: str) -> Optional[dict[str, Any]]:
        """Return the raw registry entry for ``source_id``, or ``None``."""
        return self._by_id.get(source_id)


def resolve_license(registry: SourceRegistry, source_id: str) -> LicenseResolution:
    """Resolve the licence for one curated record's source.

    Args:
        registry: A loaded, indexed source registry.
        source_id: The registry ``source_id`` this record came from (e.g.
            ``"chembl"``).

    Returns:
        The resolution. Only ``sources`` (not ``excluded_sources`` or
        ``deferred_sources``) can resolve -- a source deliberately excluded
        or not yet ingested must never silently resolve as usable.
    """
    entry = registry.get(source_id)
    if entry is None:
        return LicenseResolution(
            source_id=source_id,
            spdx=None,
            tier=None,
            commercial_ok=None,
            attribution=None,
            license_status="unresolved",
            reason=f"source_id {source_id!r} not found in the active sources registry",
        )

    licence = entry.get("license")
    if not isinstance(licence, dict):
        return LicenseResolution(
            source_id=source_id,
            spdx=None,
            tier=None,
            commercial_ok=None,
            attribution=None,
            license_status="unresolved",
            reason=f"source_id {source_id!r} has no licence block in the registry",
        )

    commercial_ok = licence.get("commercial_ok")
    spdx = licence.get("spdx")
    tier = licence.get("tier")
    if commercial_ok is None or spdx is None or tier is None:
        return LicenseResolution(
            source_id=source_id,
            spdx=spdx,
            tier=tier,
            commercial_ok=commercial_ok,
            attribution=licence.get("attribution"),
            license_status="unresolved",
            reason=(
                f"source_id {source_id!r}'s licence block is missing one of "
                "spdx/tier/commercial_ok -- never assumed"
            ),
        )

    return LicenseResolution(
        source_id=source_id,
        spdx=spdx,
        tier=tier,
        commercial_ok=bool(commercial_ok),
        attribution=licence.get("attribution"),
        license_status="resolved",
    )
