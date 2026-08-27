"""The explainable data-quality score.

Not an "AI quality score" — every component is a plain, inspectable
fraction or boolean computed from fields that genuinely exist in the
curation ledger, with a fixed, documented weight. Given the same inputs,
the same score comes out every time; there is nothing in this module that
could not be recomputed by hand from the ledger CSV.

This is deliberately two separate things, not one conflated number:

* :func:`compute_quality_score` — a continuous 0-1 score, reported for
  *every* compound, including ones that are training-ineligible. A
  discordant compound still gets a score (usually a low one, because
  ``measurement_consistency`` drops to 0) rather than disappearing —
  "don't hide discarded data."
* ``training_eligible`` — a separate hard boolean gate, decided in
  :mod:`drugsim_curation.curated_view`, not derived from this score. A
  compound is never made trainable just because its score happens to be
  high, and never excluded just because its score happens to be low.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["QUALITY_SCORE_WEIGHTS", "QualityScoreBreakdown", "compute_quality_score"]

#: Component weights, summing to 1.0. Each is a real, named contributor —
#: changing one here changes the score's meaning and should be treated the
#: same as any other versioned pipeline-rule change.
QUALITY_SCORE_WEIGHTS: dict[str, float] = {
    "structure_validity": 0.25,
    "unit_resolution_rate": 0.15,
    "license_resolution": 0.15,
    "measurement_consistency": 0.20,
    "duplicate_resolution": 0.10,
    "assay_context_coverage": 0.10,
    "provenance_completeness": 0.05,
}


@dataclass(frozen=True)
class QualityScoreBreakdown:
    """Every component of one compound's quality score, plus the total.

    Attributes:
        structure_validity: 1.0 if the structure parsed and standardised
            without error and is not a flagged mixture, else 0.0.
        unit_resolution_rate: Fraction of this compound's measurement
            *candidates* (valid structure, uncensored, not
            validity-flagged) whose unit resolved. Not restricted to the
            measurements actually used in aggregation — a compound that
            had to discard several unresolvable-unit measurements should
            visibly score lower here, even though the ones it did use are
            individually fine.
        license_resolution: Same candidate population, fraction with a
            resolved licence.
        measurement_consistency: 1.0 unless the aggregate was discordant
            (mirrors ``aggregate_continuous``'s existing >10x boundary —
            no separate invented threshold), in which case 0.0.
        duplicate_resolution: 1.0 today for both live single-source
            (ChEMBL-only) endpoints, since exact/salt-form duplicates are
            already resolved by standardisation + InChIKey grouping before
            this score is ever computed. This component becomes load-
            bearing once ``drugsim_quality.dedup.find_measurement_duplicates``
            is exercised against a genuine multi-source dataset with
            duplicates that need active resolution rather than
            structural merging.
        assay_context_coverage: Fraction of the measurements actually used
            in aggregation that have a non-null organism or paradigm
            classification.
        provenance_completeness: 1.0 if at least one contributing
            measurement has a known publication year, else 0.0.
        total: The weighted sum, using :data:`QUALITY_SCORE_WEIGHTS`.
    """

    structure_validity: float
    unit_resolution_rate: float
    license_resolution: float
    measurement_consistency: float
    duplicate_resolution: float
    assay_context_coverage: float
    provenance_completeness: float
    total: float


def compute_quality_score(
    *,
    structure_validity: float,
    unit_resolution_rate: float,
    license_resolution: float,
    measurement_consistency: float,
    duplicate_resolution: float,
    assay_context_coverage: float,
    provenance_completeness: float,
) -> QualityScoreBreakdown:
    """Combine the named components into one explainable 0-1 score.

    Each argument must already be a 0-1 value — this function only weights
    and sums, it does not itself decide what any component means (see each
    field's docstring on :class:`QualityScoreBreakdown` for that).

    Returns:
        The full breakdown, including the weighted total, so a report can
        show its arithmetic rather than just the final number.
    """
    components = {
        "structure_validity": structure_validity,
        "unit_resolution_rate": unit_resolution_rate,
        "license_resolution": license_resolution,
        "measurement_consistency": measurement_consistency,
        "duplicate_resolution": duplicate_resolution,
        "assay_context_coverage": assay_context_coverage,
        "provenance_completeness": provenance_completeness,
    }
    total = sum(components[name] * weight for name, weight in QUALITY_SCORE_WEIGHTS.items())
    return QualityScoreBreakdown(total=round(total, 4), **components)
