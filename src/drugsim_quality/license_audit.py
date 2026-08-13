"""Dataset licence audit.

Implements rules LC-01 … LC-06 (Phase 1 Step 8 §10.3) against
``datasets/registry.yaml``, the Z0 source registry.

This runs as a required CI check. Without it, licence discipline decays into a
document nobody reads — and the exposure is real: ChEMBL, DrugCentral, PharmGKB and
part of BindingDB carry ShareAlike, and FreeSolv ships inside Therapeutics Data
Commons under a non-commercial licence where it is easy to ingest by accident
(Phase 1 Step 1 §5).

The audit is deliberately strict. A licence error discovered at due diligence, two
years and one funding round later, is far more expensive than a failed build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml

__all__ = [
    "AuditResult",
    "LicenseTier",
    "TIER_BY_SPDX",
    "audit_registry",
    "build_attribution_manifest",
    "load_registry",
]


class LicenseTier(str, Enum):
    """Licence tier (Phase 1 Step 1 §5.1, TDS §4.1)."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"
    BLACK = "black"
    MIXED = "mixed"


#: Normative SPDX-to-tier mapping (Phase 1 data dictionary §C.2).
TIER_BY_SPDX: dict[str, LicenseTier] = {
    "CC0-1.0": LicenseTier.GREEN,
    "US-PD": LicenseTier.GREEN,
    "PDDL-1.0": LicenseTier.GREEN,
    "CC-BY-4.0": LicenseTier.AMBER,
    "CC-BY-3.0": LicenseTier.AMBER,
    "CC-BY-SA-4.0": LicenseTier.RED,
    "CC-BY-SA-3.0": LicenseTier.RED,
    "CC-BY-NC-SA-4.0": LicenseTier.BLACK,
    "CC-BY-NC-4.0": LicenseTier.BLACK,
    "PROPRIETARY": LicenseTier.BLACK,
    "UNKNOWN": LicenseTier.BLACK,
}

#: Tiers permitting commercial use.
_COMMERCIAL_TIERS = {LicenseTier.GREEN, LicenseTier.AMBER, LicenseTier.RED}

#: Tiers carrying a ShareAlike obligation.
_SHAREALIKE_TIERS = {LicenseTier.RED}


@dataclass
class AuditResult:
    """Outcome of a licence audit.

    Attributes:
        errors: Rule violations. Any error fails the build.
        warnings: Advisories that do not fail the build.
        sources_checked: Number of active source entries examined.
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources_checked: int = 0

    @property
    def passed(self) -> bool:
        """Whether the audit passed."""
        return not self.errors


def load_registry(path: Path) -> dict[str, Any]:
    """Load and minimally validate the source registry.

    Args:
        path: Path to ``registry.yaml``.

    Returns:
        The parsed registry.

    Raises:
        FileNotFoundError: If the registry is absent.
        ValueError: If the registry is not a mapping or lacks ``sources``.
    """
    if not path.exists():
        msg = f"source registry not found at {path}"
        raise FileNotFoundError(msg)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        msg = f"registry at {path} must be a mapping"
        raise ValueError(msg)
    if "sources" not in data:
        msg = f"registry at {path} has no 'sources' key"
        raise ValueError(msg)
    return data


def _tier_of(raw: Optional[str]) -> Optional[LicenseTier]:
    """Coerce a raw tier string to a :class:`LicenseTier`, or ``None``."""
    if raw is None:
        return None
    try:
        return LicenseTier(raw)
    except ValueError:
        return None


def _audit_license_block(
    source_id: str,
    licence: dict[str, Any],
    result: AuditResult,
    *,
    context: str = "",
) -> None:
    """Audit one licence block against the LC rules.

    Args:
        source_id: Source identifier, for error messages.
        licence: The ``license`` mapping from a registry entry.
        result: Accumulator mutated in place.
        context: Optional suffix identifying a split-licence portion.
    """
    label = f"{source_id}{context}"
    spdx = licence.get("spdx")
    declared_tier = _tier_of(licence.get("tier"))
    commercial_ok = licence.get("commercial_ok")

    # LC-01: every source declares a licence.
    if spdx is None:
        result.errors.append(f"LC-01 {label}: no SPDX identifier declared")
        return
    if declared_tier is None:
        result.errors.append(f"LC-01 {label}: no valid tier declared")
        return

    # MIXED is only legitimate when the entry enumerates its portions.
    if spdx == "MIXED":
        return

    # LC-02: declared tier must match the normative SPDX mapping.
    expected = TIER_BY_SPDX.get(spdx)
    if expected is None:
        result.errors.append(
            f"LC-02 {label}: SPDX {spdx!r} is not in the normative tier mapping. "
            "Add it to TIER_BY_SPDX after legal review."
        )
        return
    if declared_tier != expected:
        result.errors.append(
            f"LC-02 {label}: tier {declared_tier.value!r} contradicts SPDX {spdx!r}, "
            f"which maps to {expected.value!r}"
        )

    # LC-03: the commercial flag must follow from the tier, not be asserted.
    if commercial_ok is not None:
        implied = expected in _COMMERCIAL_TIERS
        if bool(commercial_ok) != implied:
            result.errors.append(
                f"LC-03 {label}: commercial_ok={commercial_ok} contradicts tier "
                f"{expected.value!r} (implies {implied})"
            )

    # LC-02b: ShareAlike must be declared wherever it applies. Under-declaring is the
    # dangerous direction — it hides copyleft exposure.
    declared_sa = licence.get("sharealike")
    if declared_sa is not None:
        implied_sa = expected in _SHAREALIKE_TIERS
        if bool(declared_sa) != implied_sa:
            result.errors.append(
                f"LC-02 {label}: sharealike={declared_sa} contradicts SPDX {spdx!r} "
                f"(implies {implied_sa})"
            )

    # LC-05: attribution text is required wherever attribution is required.
    if expected in {LicenseTier.AMBER, LicenseTier.RED} and not licence.get("attribution"):
        result.errors.append(
            f"LC-05 {label}: {spdx} requires attribution but none is declared"
        )


def audit_registry(registry: dict[str, Any]) -> AuditResult:
    """Audit the source registry against rules LC-01 … LC-06.

    Args:
        registry: Parsed registry mapping.

    Returns:
        The audit result.
    """
    result = AuditResult()

    for source in registry.get("sources") or []:
        source_id = source.get("source_id", "<unnamed>")
        result.sources_checked += 1

        licence = source.get("license")
        if not isinstance(licence, dict):
            result.errors.append(f"LC-01 {source_id}: no license block")
            continue

        _audit_license_block(source_id, licence, result)

        # A MIXED source must enumerate its licensing. Two legitimate shapes exist,
        # reflecting two genuinely different situations:
        #
        #   split_licensing        — the source itself is internally split, with no
        #                            single default. BindingDB: its own curation is
        #                            CC BY 3.0, its ChEMBL-derived portion CC BY-SA
        #                            3.0. This is why per-record licence tracking
        #                            exists at all (ADR-007).
        #   default_* + exclusions — a uniform default with carve-outs. TDC: mostly
        #                            CC BY 4.0, but FreeSolv is CC BY-NC-SA 4.0 and
        #                            ships behind the same uniform interface, which
        #                            is exactly what makes it easy to ingest by
        #                            accident.
        portions = licence.get("split_licensing")
        exclusions = licence.get("exclusions")
        if licence.get("spdx") == "MIXED" and not portions and not exclusions:
            result.errors.append(
                f"LC-01 {source_id}: declared MIXED but enumerates neither "
                "'split_licensing' portions nor a 'default_spdx' with 'exclusions'. "
                "A dataset-level tag is provably insufficient for mixed licensing."
            )
        for portion in portions or []:
            _audit_license_block(
                source_id, portion, result, context=f"[{portion.get('portion', '?')}]"
            )

        # Validate the default arm of a default+exclusions source.
        default_spdx = licence.get("default_spdx")
        if default_spdx is not None:
            _audit_license_block(
                source_id,
                {
                    "spdx": default_spdx,
                    "tier": licence.get("default_tier"),
                    "attribution": licence.get("attribution"),
                },
                result,
                context="[default]",
            )

        # Exclusions carved out of an otherwise usable source must be black-tier.
        for exclusion in licence.get("exclusions") or []:
            excl_tier = _tier_of(exclusion.get("tier"))
            if excl_tier is not LicenseTier.BLACK:
                result.errors.append(
                    f"LC-03 {source_id}[{exclusion.get('dataset', '?')}]: an exclusion "
                    f"must be black-tier, found {exclusion.get('tier')!r}"
                )
            if exclusion.get("commercial_ok") is not False:
                result.errors.append(
                    f"LC-03 {source_id}[{exclusion.get('dataset', '?')}]: an exclusion "
                    "must set commercial_ok: false"
                )

        # LC-04: staleness is an advisory, not a failure — but must be visible.
        cadence = source.get("cadence") or {}
        if cadence.get("stale"):
            result.warnings.append(
                f"LC-04 {source_id}: marked stale — {cadence.get('stale_reason', 'no reason given')}"
            )

        verification = source.get("verification") or {}
        if verification.get("status") == "unverified":
            result.warnings.append(
                f"{source_id}: figures unverified — {verification.get('action_required', 'verify')}"
            )

    # LC-06: excluded sources must not be commercially usable.
    for excluded in registry.get("excluded_sources") or []:
        source_id = excluded.get("source_id", "<unnamed>")
        licence = excluded.get("license") or {}
        tier = _tier_of(licence.get("tier"))
        if licence.get("commercial_ok") is True and tier is not LicenseTier.RED:
            result.errors.append(
                f"LC-06 {source_id}: listed as excluded but commercial_ok is true"
            )
        if not excluded.get("reason"):
            result.errors.append(f"LC-06 {source_id}: excluded without a recorded reason")

    return result


def build_attribution_manifest(registry: dict[str, Any]) -> str:
    """Generate the attribution manifest required by rule LC-05.

    Args:
        registry: Parsed registry mapping.

    Returns:
        A Markdown document listing every attribution obligation.
    """
    lines = [
        "# DrugSim Data Attribution Manifest",
        "",
        "Generated from `datasets/registry.yaml`. Do not edit by hand — regenerate",
        "with `make audit`. Required by rule LC-05.",
        "",
    ]
    by_tier: dict[str, list[str]] = {}
    for source in registry.get("sources") or []:
        licence = source.get("license") or {}
        tier = str(licence.get("tier", "unknown"))
        attribution = licence.get("attribution")
        entry = f"- **{source.get('name', source.get('source_id'))}** — {licence.get('spdx')}"
        if attribution:
            entry += f'\n  > {attribution}'
        by_tier.setdefault(tier, []).append(entry)

    for tier in ("green", "amber", "red", "mixed", "black"):
        if tier in by_tier:
            lines.append(f"## Tier: {tier}")
            lines.append("")
            lines.extend(by_tier[tier])
            lines.append("")
    return "\n".join(lines)
