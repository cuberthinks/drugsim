"""Measurement aggregation with discordance flags.

**Never silently average conflicting measurements.** This module computes a
*recorded, versioned decision* about what value a model trains on
(``measurement_aggregate``), kept structurally separate from the immutable
individual observations (``measurement``). A compound with 100-fold
disagreement between two labs is not a training example — it is a
data-quality finding, and this module's job is to surface that, not to
paper over it with an average (Phase 1 Step 8 §3.3).

Two policies, chosen by data type:

* **Continuous potency** (IC50/Ki/Kd/EC50): **geometric mean** of uncensored
  values. Potency is log-normally distributed — an IC50 of 1 nM and 100 nM
  are "twice as far apart" as 100 nM and 10,000 nM in the way that matters
  biologically, and the arithmetic mean badly overweights the high-value
  tail for exactly that reason.
* **Other continuous** (ADMET properties): **median**, robust to outliers
  without needing a log-normality assumption that may not hold.
* **Binary**: **majority vote**; an exact tie is discordant, not a coin flip.

Discordance: continuous values spanning more than 10x (``value_spread_log10
> 1``) or a binary tie are flagged ``is_discordant`` and excluded from
training — never forced into a single confident number.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass
from typing import Literal

__all__ = ["AggregationResult", "aggregate_binary", "aggregate_continuous"]

#: Values spanning more than one order of magnitude are discordant.
_DISCORDANCE_THRESHOLD_LOG10 = 1.0

AggregationMethod = Literal["single_value", "median", "geometric_mean", "majority_vote"]


@dataclass(frozen=True)
class AggregationResult:
    """The outcome of aggregating one compound+endpoint's measurements.

    Attributes:
        aggregated_value: The computed value. For a discordant result this is
            still populated (e.g. the median, or the majority-vote fraction)
            so the number is inspectable — but ``is_discordant=True`` means
            it must not be used for training regardless.
        method: Which aggregation rule was applied.
        n_source_measurements: How many individual observations went in.
        value_spread_log10: For continuous aggregation, ``log10(max/min)``
            over the uncensored inputs. ``None`` for binary or single-value
            cases, where the concept does not apply.
        is_discordant: Whether this result must be excluded from training.
    """

    aggregated_value: float
    method: AggregationMethod
    n_source_measurements: int
    value_spread_log10: float | None
    is_discordant: bool


def aggregate_continuous(
    values: list[float],
    *,
    is_potency: bool,
    discordance_threshold_log10: float = _DISCORDANCE_THRESHOLD_LOG10,
) -> AggregationResult:
    """Aggregate continuous, uncensored measurements for one compound+endpoint.

    Args:
        values: Uncensored (``value_relation = '='``), measured (not
            predicted) values, already unit-harmonised. Must all be positive
            if ``is_potency`` is True — potency values are always positive
            concentrations, and the geometric mean is undefined otherwise.
        is_potency: True for IC50/Ki/Kd/EC50-style values (geometric mean);
            False for other continuous endpoints (median).
        discordance_threshold_log10: Spread above which the result is
            discordant. Default matches Phase 1 Step 8 §3.3's ">10x
            disagreement" rule (``log10(10) == 1``).

    Returns:
        The aggregation result.

    Raises:
        ValueError: If ``values`` is empty, or if ``is_potency`` is True and
            any value is non-positive (a non-positive potency value is
            itself invalid data, not something to silently coerce).
    """
    if not values:
        msg = "cannot aggregate an empty value list"
        raise ValueError(msg)

    if len(values) == 1:
        return AggregationResult(
            aggregated_value=values[0],
            method="single_value",
            n_source_measurements=1,
            value_spread_log10=0.0,
            is_discordant=False,
        )

    if is_potency and any(v <= 0 for v in values):
        msg = "potency values must be strictly positive for geometric mean aggregation"
        raise ValueError(msg)

    # Two distinct spread conventions, not one formula stretched to cover both:
    #
    # - All values strictly positive (potency; and most other continuous
    #   endpoints too — half-life, VDss, clearance are all positive physical
    #   quantities): a true ratio, log10(max/min). ">10x" is well-defined.
    # - Some value <= 0 (already-log-scale quantities that can be negative,
    #   e.g. logD, logS): log10(max/min) is undefined. Absolute difference
    #   between the extremes is used instead, on the SAME numeric threshold —
    #   "differ by more than 1 log-unit" is the natural analogue of ">10x"
    #   for a quantity that is already a logarithm.
    if all(v > 0 for v in values):
        spread_log10 = math.log10(max(values) / min(values))
    else:
        spread_log10 = max(values) - min(values)
    is_discordant = spread_log10 > discordance_threshold_log10

    if is_potency:
        log_values = [math.log10(v) for v in values]
        aggregated = 10 ** statistics.mean(log_values)
        method: AggregationMethod = "geometric_mean"
    else:
        aggregated = statistics.median(values)
        method = "median"

    return AggregationResult(
        aggregated_value=aggregated,
        method=method,
        n_source_measurements=len(values),
        value_spread_log10=round(spread_log10, 4),
        is_discordant=is_discordant,
    )


def aggregate_binary(labels: list[bool]) -> AggregationResult:
    """Aggregate binary classification measurements by majority vote.

    Args:
        labels: Individual binary observations (e.g. Ames positive/negative).

    Returns:
        ``aggregated_value`` is 1.0 or 0.0 for a clear majority, or 0.5 for an
        exact tie. A tie is **always** discordant — there is no meaningful
        "majority" to report, and 0.5 must never be interpreted as a
        probability.

    Raises:
        ValueError: If ``labels`` is empty.
    """
    if not labels:
        msg = "cannot aggregate an empty label list"
        raise ValueError(msg)

    if len(labels) == 1:
        return AggregationResult(
            aggregated_value=float(labels[0]),
            method="single_value",
            n_source_measurements=1,
            value_spread_log10=None,
            is_discordant=False,
        )

    counts = Counter(labels)
    positive = counts.get(True, 0)
    negative = counts.get(False, 0)
    is_tie = positive == negative

    if is_tie:
        aggregated = 0.5
    else:
        aggregated = 1.0 if positive > negative else 0.0

    return AggregationResult(
        aggregated_value=aggregated,
        method="majority_vote",
        n_source_measurements=len(labels),
        value_spread_log10=None,
        is_discordant=is_tie,
    )
