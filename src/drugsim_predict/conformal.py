"""Split conformal prediction (TDS Sec 6.7), using the frozen calibration split.

**Precision, not a stylistic choice**: split conformal coverage is a
*marginal, population-level guarantee* under exchangeability with the
calibration set — "the true label falls in the predicted set at a target
rate, averaged over many predictions from an exchangeable population." It is
**not** a per-instance probability that any single prediction is correct.
Phase 4 (``06_uncertainty_calibration.py``) confirmed empirically that this
marginal guarantee survives even a substantial class-prevalence shift, while
the model's raw pointwise probability calibration does not — which is
exactly why this module returns a prediction *set* and a p-value per class,
never a bare "confidence percentage" framed as per-instance correctness.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from drugsim_predict.model_registry import ModelBundle

__all__ = ["METHOD_NAME", "ConformalResult", "compute_conformal_set"]

#: Phase 10 Sec 4 finding: a prediction must be traceable to its uncertainty
#: methodology from its OWN response, not only via a separate registry
#: lookup by model_id (the same self-description standard already applied
#: to model_id/version/checksum in ProvenanceSchema). One constant because
#: every currently-registered endpoint uses this exact method; a future
#: endpoint using a different one would need its own value threaded through
#: here rather than this becoming silently wrong.
METHOD_NAME = "split_conformal_prediction"


@dataclass(frozen=True)
class ConformalResult:
    """A conformal prediction set at the bundle's nominal confidence.

    Attributes:
        predicted_set: Which class labels (the endpoint's own positive/
            negative vocabulary, e.g. "blocker"/"non_blocker" for hERG or
            "inhibitor"/"non_inhibitor" for CYP3A4 — Phase 9 genericisation,
            see :class:`~drugsim_predict.model_registry.ModelBundle`) remain
            plausible at the nominal confidence level. A set of size 2 means
            the model cannot distinguish the classes for this input at the
            target confidence — itself informative, not a defect.
        p_value_blocker: Conformal p-value for the positive-class label.
            Field name kept from hERG (the first endpoint) for wire
            compatibility — see ``EstimateSchema.predicted_probability_blocker``
            for the same convention; the *value* is correct for every
            endpoint, only the name is a legacy holdover.
        p_value_non_blocker: Conformal p-value for the negative-class label
            (same naming note as above).
        nominal_confidence: The target coverage rate this set is calibrated to.
        is_singleton: Whether exactly one class remains — the model's most
            confident, unambiguous output shape.
    """

    predicted_set: tuple[str, ...]
    p_value_blocker: float
    p_value_non_blocker: float
    nominal_confidence: float
    is_singleton: bool
    method: str = METHOD_NAME


def compute_conformal_set(class_probabilities: np.ndarray, bundle: ModelBundle) -> ConformalResult:
    """Compute the conformal prediction set for one query's class probabilities.

    Args:
        class_probabilities: ``[P(negative_class), P(positive_class)]`` from
            the registered model's ``predict_proba`` — column order matches
            ``sklearn``'s ``classes_`` attribute, ``[0, 1]``.
        bundle: The loaded, verified model bundle, providing the frozen
            calibration nonconformity distribution and the endpoint's own
            label vocabulary.

    Returns:
        The conformal result.
    """
    epsilon = 1.0 - bundle.nominal_confidence
    n_cal = len(bundle.calibration_nonconformity)

    def _p_value(candidate_prob: float) -> float:
        alpha_candidate = 1.0 - candidate_prob
        count = int((bundle.calibration_nonconformity >= alpha_candidate).sum())
        return (count + 1) / (n_cal + 1)

    p_negative = _p_value(class_probabilities[0])
    p_positive = _p_value(class_probabilities[1])

    labels = []
    if p_negative > epsilon:
        labels.append(bundle.negative_class_label)
    if p_positive > epsilon:
        labels.append(bundle.positive_class_label)

    return ConformalResult(
        predicted_set=tuple(labels),
        p_value_blocker=round(p_positive, 4),
        p_value_non_blocker=round(p_negative, 4),
        nominal_confidence=bundle.nominal_confidence,
        is_singleton=len(labels) == 1,
    )
