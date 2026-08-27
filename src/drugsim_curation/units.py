"""Per-record unit resolution.

ADR-012 (Phase 1 Step 2 §10) says every measurement should carry its
original value/unit verbatim *and* a normalised value/unit plus the
conversion method applied — never a single collapsed number with the
original discarded. The live ``build_dataset.py`` pipelines don't need this
today because their ChEMBL API queries already filter to ``standard_units
== "nM"`` at the source, so no real multi-unit data reaches them. This
module is what a per-record field actually requires once that stops being
true — the day a second, non-pre-filtered source is added, this is the
code that decides whether a value can be trusted on a common scale.

**If a unit cannot be established reliably, this module marks it
unresolved. It never guesses.** A molar-concentration unit (nM, uM, mM, M,
pM) converts to nM by a fixed, unambiguous factor. A mass-concentration
unit (ug/mL, mg/mL, ng/mL) requires the compound's molecular weight to
convert to a molar basis — if that isn't supplied, the value is marked
``unresolved`` and excluded from training rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

__all__ = ["UnitResolution", "resolve_unit"]

UnitStatus = Literal["resolved", "unresolved"]
ConversionStatus = Literal["not_required", "converted", "unresolved_no_molecular_weight", "unresolved_unknown_unit"]

#: Molar-concentration units with an unambiguous, MW-independent factor to nM.
_MOLAR_TO_NM: dict[str, float] = {
    "nM": 1.0,
    "uM": 1_000.0,
    "µM": 1_000.0,
    "mM": 1_000_000.0,
    "M": 1_000_000_000.0,
    "pM": 0.001,
}

#: Mass-concentration units that require a molecular weight to convert.
#: Values are the multiplier to convert 1 unit of "mass/mL" to grams per
#: litre: e.g. 1 ug/mL = 1e-6 g / 1e-3 L = 1e-3 g/L, so ug/mL's factor is
#: 1e-3 -- verified against a worked example in
#: tests/unit/test_curation_units.py, not just derived on paper.
_MASS_CONCENTRATION_TO_G_PER_L: dict[str, float] = {
    "ug.mL-1": 0.001,
    "ug/mL": 0.001,
    "mg.mL-1": 1.0,
    "mg/mL": 1.0,
    "ng.mL-1": 0.000_001,
    "ng/mL": 0.000_001,
}


@dataclass(frozen=True)
class UnitResolution:
    """The outcome of resolving one measurement's unit.

    Attributes:
        original_value: The verbatim source value, as a string (never
            reparsed lossily before this point — the record of what the
            source actually said).
        original_unit: The verbatim source unit string.
        normalised_value: Value in nanomolar, or ``None`` if unresolved.
        normalised_unit: Always ``"nM"`` when resolved, else ``None``.
        conversion_method: Human-readable description of what was applied.
        conversion_status: Machine-readable outcome.
        unit_status: ``"resolved"`` or ``"unresolved"`` — the field a
            downstream consumer should actually branch on.
    """

    original_value: str
    original_unit: str
    normalised_value: Optional[float]
    normalised_unit: Optional[str]
    conversion_method: str
    conversion_status: ConversionStatus
    unit_status: UnitStatus


def resolve_unit(
    original_value: str,
    original_unit: str,
    *,
    molecular_weight_g_mol: Optional[float] = None,
) -> UnitResolution:
    """Resolve one measurement's value/unit onto a common nanomolar scale.

    Args:
        original_value: The verbatim source value string. Must parse as a
            float, or the resolution is unresolved (a value that isn't
            even numeric cannot be unit-resolved regardless of the unit).
        original_unit: The verbatim source unit string (e.g. ChEMBL's
            ``standard_units``).
        molecular_weight_g_mol: The compound's molecular weight, if known —
            only needed to convert a mass-concentration unit (ug/mL etc.)
            to a molar basis. ``None`` means that conversion is not
            attempted, per this module's "never guess" rule.

    Returns:
        The resolution. ``unit_status == "unresolved"`` covers: an
        unparseable value, an unrecognised unit string, or a
        mass-concentration unit with no molecular weight supplied.
    """
    try:
        value = float(original_value)
    except (TypeError, ValueError):
        return UnitResolution(
            original_value=original_value,
            original_unit=original_unit,
            normalised_value=None,
            normalised_unit=None,
            conversion_method="none -- value did not parse as a number",
            conversion_status="unresolved_unknown_unit",
            unit_status="unresolved",
        )

    if original_unit in _MOLAR_TO_NM:
        factor = _MOLAR_TO_NM[original_unit]
        method = "identity_nm_passthrough" if factor == 1.0 else f"molar_unit_conversion(*{factor})"
        status: ConversionStatus = "not_required" if factor == 1.0 else "converted"
        return UnitResolution(
            original_value=original_value,
            original_unit=original_unit,
            normalised_value=value * factor,
            normalised_unit="nM",
            conversion_method=method,
            conversion_status=status,
            unit_status="resolved",
        )

    if original_unit in _MASS_CONCENTRATION_TO_G_PER_L:
        if molecular_weight_g_mol is None or molecular_weight_g_mol <= 0:
            return UnitResolution(
                original_value=original_value,
                original_unit=original_unit,
                normalised_value=None,
                normalised_unit=None,
                conversion_method=(
                    f"mass-concentration unit {original_unit!r} requires a molecular weight "
                    "to convert to a molar basis; none was supplied"
                ),
                conversion_status="unresolved_no_molecular_weight",
                unit_status="unresolved",
            )
        g_per_l = value * _MASS_CONCENTRATION_TO_G_PER_L[original_unit]
        molar = g_per_l / molecular_weight_g_mol  # mol/L == M
        return UnitResolution(
            original_value=original_value,
            original_unit=original_unit,
            normalised_value=molar * _MOLAR_TO_NM["M"],
            normalised_unit="nM",
            conversion_method=f"mass_to_molar(mw={molecular_weight_g_mol}) then M->nM",
            conversion_status="converted",
            unit_status="resolved",
        )

    return UnitResolution(
        original_value=original_value,
        original_unit=original_unit,
        normalised_value=None,
        normalised_unit=None,
        conversion_method=f"unit {original_unit!r} is not in the known conversion table",
        conversion_status="unresolved_unknown_unit",
        unit_status="unresolved",
    )
