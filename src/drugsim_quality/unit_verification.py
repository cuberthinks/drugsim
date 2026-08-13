"""Empirical unit verification — gate G4.

Exists because Therapeutics Data Commons does not document units for most
ADME/Tox endpoints (Phase 1 Step 1, verified 2026-08-05) — and per this
project's explicit rule, **units are never guessed**. Where documentation is
silent, correctness is asserted from the data itself: range against a
literature-derived envelope, distribution shape (log-scaled quantities are
approximately symmetric; linear-scale concentrations are heavily right-skewed),
and reference-compound sign-convention checks. An endpoint that fails every
check is marked ``unverified`` and excluded from training — not guessed at.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "ReferenceCompoundCheck",
    "UnitVerificationResult",
    "verify_range",
    "verify_reference_compounds",
    "verify_skewness_consistent_with_log_scale",
]


@dataclass(frozen=True)
class UnitVerificationResult:
    """Outcome of one verification method against one endpoint's values.

    Attributes:
        method: Which check produced this result — matches the
            ``unit_verified_method`` enum (``range_assertion``,
            ``cross_source``, etc.) wherever the two overlap.
        passed: Whether the check supports the assumed unit/scale.
        detail: Human-readable explanation, always populated — a verification
            result with no stated reasoning is not auditable.
    """

    method: str
    passed: bool
    detail: str


def verify_range(
    values: list[float],
    *,
    expected_min: float,
    expected_max: float,
    tolerance_fraction: float = 0.05,
) -> UnitVerificationResult:
    """Check observed values fall within a literature-derived envelope.

    Args:
        values: Observed values, already excluding censored/missing records.
        expected_min: Literature-derived lower bound for the assumed unit.
        expected_max: Literature-derived upper bound.
        tolerance_fraction: Fraction of values permitted to fall outside the
            envelope before the check fails — real data always has some
            outliers, so a zero-tolerance check would reject every real
            dataset regardless of whether the units are actually right.

    Returns:
        The verification result.

    Raises:
        ValueError: If ``values`` is empty — there is nothing to verify.
    """
    if not values:
        msg = "cannot verify an empty value list"
        raise ValueError(msg)

    out_of_range = sum(1 for v in values if v < expected_min or v > expected_max)
    fraction_out = out_of_range / len(values)
    passed = fraction_out <= tolerance_fraction

    detail = (
        f"{out_of_range}/{len(values)} values ({fraction_out:.1%}) outside "
        f"[{expected_min}, {expected_max}]; tolerance {tolerance_fraction:.1%}"
    )
    return UnitVerificationResult(method="range_assertion", passed=passed, detail=detail)


def _sample_skewness(values: list[float]) -> float:
    """Compute Fisher-Pearson sample skewness.

    Args:
        values: At least 3 values (skewness is undefined below that).

    Returns:
        The skewness. Zero for a symmetric distribution; large positive
        values indicate a long right tail, characteristic of untransformed
        concentration data.

    Raises:
        ValueError: If fewer than 3 values, or all values are identical
            (zero variance makes skewness undefined, not zero).
    """
    n = len(values)
    if n < 3:
        msg = f"skewness requires at least 3 values, got {n}"
        raise ValueError(msg)
    mean = statistics.mean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        msg = "all values identical — skewness is undefined, not zero"
        raise ValueError(msg)
    m3 = sum((v - mean) ** 3 for v in values) / n
    return m3 / (stdev**3)


def verify_skewness_consistent_with_log_scale(
    values: list[float],
    *,
    assumed_log_scale: bool,
    skew_threshold: float = 2.0,
) -> UnitVerificationResult:
    """Check whether a value distribution's shape matches the assumed scale.

    Log-scaled quantities (pIC50, logD, logS) are approximately symmetric.
    Linear-scale concentrations are heavily right-skewed — a handful of very
    potent/soluble outliers stretch the tail. A high-skew sample presented as
    already log-transformed is exactly the shape a raw-mol/L-labelled-as-log
    unit error would produce.

    Args:
        values: Observed values.
        assumed_log_scale: Whether the endpoint is assumed to already be on a
            log scale.
        skew_threshold: Absolute skewness above which a "log scale" claim is
            considered inconsistent with the data's actual shape.

    Returns:
        The verification result. Labelled ``method="range_assertion"``, the
        same as :func:`verify_range` — the DB's ``unit_verified_method`` enum
        has four coarse categories (``documented``, ``range_assertion``,
        ``cross_source``, ``unverified``), not one per check in Phase 1 Step
        2 §5's five-method description. Both range and distribution-shape
        checks are "derived from this dataset's own statistical properties
        without an external source", so both map to ``range_assertion``.
    """
    skew = _sample_skewness(values)
    if assumed_log_scale:
        passed = abs(skew) <= skew_threshold
        detail = (
            f"skewness={skew:.2f}; log-scaled data should be approximately "
            f"symmetric (|skew|<={skew_threshold}), consistent={passed}"
        )
    else:
        # A linear-scale endpoint being symmetric is not itself an error —
        # only used as a secondary signal, so this direction never fails.
        passed = True
        detail = f"skewness={skew:.2f}; linear-scale data, no symmetry expectation"
    return UnitVerificationResult(method="range_assertion", passed=passed, detail=detail)


@dataclass(frozen=True)
class ReferenceCompoundCheck:
    """One reference compound's expected vs. observed value."""

    compound_name: str
    expected_value: float
    observed_value: float
    tolerance_log10: float = 1.0


def verify_reference_compounds(
    checks: list[ReferenceCompoundCheck],
) -> UnitVerificationResult:
    """Check observed values against literature-established reference compounds.

    **This is the only method that reliably catches a sign inversion.**
    Phase 1 Step 2 §G.1 identified LD50's sign convention as the highest-risk
    conversion in the system: `log(1/(mol/kg))` has higher values meaning
    MORE toxic, the inverse of intuition. A sign inversion trains cleanly,
    converges, and reports plausible-looking metrics — the distribution is
    symmetric under negation, so neither the range check nor the skewness
    check can distinguish an inverted scale from a correct one. Only
    asserting that a known-toxic reference compound actually ranks as toxic
    (or a known-safe one as safe) catches it.

    Args:
        checks: Reference compounds with known literature values, compared
            in log10 space (so a comparison works uniformly whether the
            underlying quantity is linear or log-scale).

    Returns:
        The verification result. Fails if any reference compound's observed
        value falls outside its tolerance.

    Raises:
        ValueError: If ``checks`` is empty.
    """
    if not checks:
        msg = "cannot verify with an empty reference compound list"
        raise ValueError(msg)

    failures: list[str] = []
    for check in checks:
        if check.expected_value <= 0 or check.observed_value <= 0:
            # Values that can be negative or zero (e.g. already-log-scaled
            # quantities) are compared directly, not via log10.
            diff = abs(check.expected_value - check.observed_value)
            ok = diff <= check.tolerance_log10
        else:
            diff = abs(math.log10(check.expected_value) - math.log10(check.observed_value))
            ok = diff <= check.tolerance_log10
        if not ok:
            failures.append(
                f"{check.compound_name}: expected {check.expected_value}, "
                f"got {check.observed_value} (diff {diff:.2f} > tolerance {check.tolerance_log10})"
            )

    passed = not failures
    detail = "all reference compounds within tolerance" if passed else "; ".join(failures)
    return UnitVerificationResult(method="cross_source", passed=passed, detail=detail)
