"""Applicability domain assessment (TDS Sec 6.8).

Three components, combined exactly per the verdict table validated in
Phase 3 (``models/admet/herg_inhibition/reliability.py``) and re-checked in
Phase 4 (``phase4/05_applicability_domain.py``):

  * max Tanimoto similarity to the training set (structural novelty)
  * k-NN distance in standardised descriptor space (descriptor-space novelty)
  * whether the query's Bemis-Murcko scaffold was seen in training

All three are computed against the FROZEN training reference data in the
loaded :class:`~drugsim_predict.model_registry.ModelBundle` — never against
a query-time recomputation of "the training set", which would silently
drift if the underlying dataset files ever changed on disk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

from drugsim_predict.model_registry import ModelBundle

__all__ = ["METHOD_NAME", "ApplicabilityDomainResult", "assess_applicability_domain"]

ADVerdict = Literal["in_domain", "borderline", "out_of_domain", "undeterminable"]

#: Phase 10 Sec 4 finding: see conformal.METHOD_NAME's docstring for why
#: this is surfaced on the result itself rather than only in the registry.
METHOD_NAME = "tanimoto_knn_distance_scaffold_membership"


@dataclass(frozen=True)
class ApplicabilityDomainResult:
    """The AD verdict plus the evidence behind it (TDS: "ad_rationale renders
    the reasoning in plain language ... a chemist can evaluate that").

    Attributes:
        verdict: One of ``in_domain``, ``borderline``, ``out_of_domain``,
            ``undeterminable``.
        max_tanimoto_to_training: Highest Morgan-fingerprint Tanimoto
            similarity to any training compound.
        knn_distance: Mean distance to the ``k`` nearest training compounds
            in standardised descriptor space.
        knn_distance_threshold: The frozen 95th-percentile training-internal
            distance this was compared against.
        scaffold_seen_in_training: Whether the query's Bemis-Murcko scaffold
            appears in the training set.
        rationale: Plain-language explanation, safe to show a chemist.
    """

    verdict: ADVerdict
    max_tanimoto_to_training: Optional[float]
    knn_distance: Optional[float]
    knn_distance_threshold: float
    scaffold_seen_in_training: Optional[bool]
    rationale: str
    method: str = METHOD_NAME


def _max_tanimoto(query_fp: np.ndarray, train_fps: np.ndarray) -> float:
    q = query_fp.astype(np.float32)
    r = train_fps.astype(np.float32)
    intersection = r @ q
    union = r.sum(axis=1) + q.sum() - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, intersection / union, 0.0)
    return float(sim.max())


def assess_applicability_domain(
    query_fingerprint: np.ndarray,
    query_descriptors: np.ndarray,
    query_scaffold: Optional[str],
    bundle: ModelBundle,
) -> ApplicabilityDomainResult:
    """Assess whether a query structure is within the model's applicability domain.

    Args:
        query_fingerprint: Morgan fingerprint of the standardised query
            structure (same 2048-bit layout as training).
        query_descriptors: Raw (unscaled) physicochemical descriptor vector,
            same order as ``bundle.descriptor_fields``.
        query_scaffold: Bemis-Murcko scaffold SMILES, or ``None`` for an
            acyclic structure (matches the fallback convention used when
            building the training scaffold set: an acyclic compound's own
            standardised SMILES stands in for its scaffold).
        bundle: The loaded, verified model bundle.

    Returns:
        The AD verdict and its supporting evidence.
    """
    if query_fingerprint is None or query_descriptors is None:
        return ApplicabilityDomainResult(
            verdict="undeterminable",
            max_tanimoto_to_training=None,
            knn_distance=None,
            knn_distance_threshold=bundle.knn_distance_threshold_p95,
            scaffold_seen_in_training=None,
            rationale="Descriptors or fingerprint could not be computed for this structure.",
        )

    max_tanimoto = _max_tanimoto(query_fingerprint, bundle.train_fingerprints)

    scaled = bundle.descriptor_ad_scaler.transform(query_descriptors.reshape(1, -1))
    train_scaled = bundle.descriptor_ad_scaler.transform(bundle.train_descriptors)
    dists = np.linalg.norm(train_scaled - scaled, axis=1)
    knn_distance = float(np.sort(dists)[: bundle.knn_k].mean())

    scaffold_seen = (query_scaffold in bundle.train_scaffolds) if query_scaffold else False

    knn_triggered = knn_distance > bundle.knn_distance_threshold_p95
    tanimoto_weak = max_tanimoto < 0.6
    scaffold_triggered = not scaffold_seen
    n_triggered = sum([tanimoto_weak, knn_triggered, scaffold_triggered])

    if max_tanimoto < 0.4:
        verdict: ADVerdict = "out_of_domain"
    elif n_triggered >= 2:
        verdict = "out_of_domain"
    elif n_triggered == 1:
        verdict = "borderline"
    else:
        verdict = "in_domain"

    rationale = (
        f"Maximum similarity to any training compound is {max_tanimoto:.2f}; "
        f"scaffold {'is' if scaffold_seen else 'is not'} present in the training set; "
        f"descriptor-space distance to nearest training neighbours is {knn_distance:.2f} "
        f"(training-internal threshold {bundle.knn_distance_threshold_p95:.2f})."
    )

    return ApplicabilityDomainResult(
        verdict=verdict,
        max_tanimoto_to_training=round(max_tanimoto, 4),
        knn_distance=round(knn_distance, 4),
        knn_distance_threshold=bundle.knn_distance_threshold_p95,
        scaffold_seen_in_training=scaffold_seen,
        rationale=rationale,
    )
