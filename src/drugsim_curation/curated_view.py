"""The per-compound curated view.

Same aggregation policy the live pipelines already use correctly
(``drugsim_quality.aggregation.aggregate_continuous`` -- geometric mean for
potency, >10x spread is discordant) -- this module does not re-decide *how*
to aggregate. What it changes is what happens *after*: a discordant
compound is **retained** here with ``training_eligible=False`` and a
recorded reason, instead of vanishing the way it does in
``build_dataset.py``'s ``if agg.is_discordant: continue``.

A note on where ``training_eligible`` diverges slightly from the original
phase plan: the plan's draft hard-gate included "100% of contributing
measurements have a resolved unit." In practice that double-counts work
already done at the measurement level -- a measurement with an unresolved
unit is already excluded from the values fed to aggregation (see
:mod:`drugsim_curation.ledger`), so it cannot silently corrupt the
aggregate. Requiring *zero* unresolved-unit siblings would make a compound
with 9 good measurements and 1 bad-unit one ineligible for no reason
related to its own aggregate. Unit-resolution shortfall is instead
reflected continuously in the quality score's ``unit_resolution_rate``
component (see :mod:`drugsim_curation.quality_score`), not as a hard gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from drugsim_quality.aggregation import aggregate_continuous

from drugsim_curation.ledger import MeasurementLedgerRow
from drugsim_curation.quality_score import QualityScoreBreakdown, compute_quality_score
from drugsim_curation.versions import CURATION_PIPELINE_VERSION

__all__ = ["CuratedCompoundRow", "build_curated_compound"]

ConflictStatus = str  # "consistent" | "discordant" | "insufficient_data"


@dataclass(frozen=True)
class CuratedCompoundRow:
    """The resolved, aggregate view for one compound.

    Attributes:
        measurement_ids: Semicolon-joined list of every contributing
            ``measurement_id`` -- the per-record provenance link back to
            raw ``activity_id``s that does not exist in today's
            ``datasets/processed/*.csv``.
        training_eligible: The hard gate -- see the module docstring for
            exactly what it requires.
        data_quality_score: 0-1, reported for every compound including
            ineligible ones -- see :mod:`drugsim_curation.quality_score`.
    """

    compound_id: str
    inchikey_full: str
    canonical_smiles: str
    standardized_smiles: str
    bemis_murcko_scaffold: str
    molecular_formula: str
    n_source_measurements_total: int
    n_source_measurements_used: int
    aggregated_ic50_nm: Optional[float]
    aggregation_method: Optional[str]
    value_spread_log10: Optional[float]
    is_discordant: bool
    conflict_status: ConflictStatus
    label: Optional[int]
    training_eligible: bool
    exclusion_reason: Optional[str]
    quality: QualityScoreBreakdown
    measurement_ids: str
    source_chembl_ids: str
    source_document_years: str
    molecule_pref_names: str
    license_spdx: Optional[str]
    license_tier: Optional[str]
    license_commercial_ok: Optional[bool]
    dataset_version: str
    curated_at: str


def build_curated_compound(
    *,
    compound_id: str,
    canonical_smiles: str,
    standardized_smiles: str,
    bemis_murcko_scaffold: str,
    molecular_formula: str,
    ledger_rows: list[MeasurementLedgerRow],
    is_potency: bool,
    blocker_threshold_nm: float,
    dataset_version: str,
    curated_at: str,
) -> CuratedCompoundRow:
    """Aggregate one compound's ledger rows into a curated compound row.

    Args:
        compound_id: The standardised ``inchikey_full`` all of
            ``ledger_rows`` share -- callers must group rows by this before
            calling (this function does not itself group).
        canonical_smiles: This compound's canonical SMILES.
        standardized_smiles: This compound's standardised SMILES.
        bemis_murcko_scaffold: This compound's scaffold, or ``""`` for an
            acyclic compound (matching ``build_dataset.py``'s convention).
        molecular_formula: This compound's Hill-notation formula.
        ledger_rows: Every ledger row sharing ``compound_id`` -- both
            included and excluded, so totals are accurate.
        is_potency: Passed through to ``aggregate_continuous`` -- True for
            IC50/Ki/Kd/EC50-style endpoints (both hERG and CYP3A4 today).
        blocker_threshold_nm: The binary-label cutoff, in nM -- endpoint's
            own documented convention (10,000 nM / 10 uM for both live
            endpoints today), passed in rather than hardcoded so this
            module makes no assumption about which endpoint it's running
            for.
        dataset_version: This curation run's dataset version string.
        curated_at: This curation run's timestamp.

    Returns:
        The curated compound row. ``label`` is computed whenever an
        aggregate exists at all, even for a discordant/ineligible compound
        -- "computed regardless of eligibility, for transparency" per the
        curation spec; ``training_eligible=False`` is what actually gates
        use, not the absence of a label.
    """
    included = [r for r in ledger_rows if r.curation_status == "included"]
    candidates = [
        r
        for r in ledger_rows
        if r.structure_status == "valid" and r.original_relation == "=" and r.exclusion_reason != "bad_validity_comment"
    ]

    if not included:
        quality = compute_quality_score(
            structure_validity=1.0,
            unit_resolution_rate=(sum(1 for r in candidates if r.unit_status == "resolved") / len(candidates)) if candidates else 0.0,
            license_resolution=(sum(1 for r in candidates if r.license_status == "resolved") / len(candidates)) if candidates else 0.0,
            measurement_consistency=0.0,
            duplicate_resolution=1.0,
            assay_context_coverage=0.0,
            provenance_completeness=0.0,
        )
        return CuratedCompoundRow(
            compound_id=compound_id,
            inchikey_full=compound_id,
            canonical_smiles=canonical_smiles,
            standardized_smiles=standardized_smiles,
            bemis_murcko_scaffold=bemis_murcko_scaffold,
            molecular_formula=molecular_formula,
            n_source_measurements_total=len(ledger_rows),
            n_source_measurements_used=0,
            aggregated_ic50_nm=None,
            aggregation_method=None,
            value_spread_log10=None,
            is_discordant=False,
            conflict_status="insufficient_data",
            label=None,
            training_eligible=False,
            exclusion_reason="no_usable_measurements",
            quality=quality,
            measurement_ids="",
            source_chembl_ids=";".join(sorted({r.molecule_chembl_id for r in ledger_rows})),
            source_document_years=";".join(sorted({r.document_year for r in ledger_rows if r.document_year})),
            molecule_pref_names="",
            license_spdx=ledger_rows[0].license_spdx if ledger_rows else None,
            license_tier=ledger_rows[0].license_tier if ledger_rows else None,
            license_commercial_ok=ledger_rows[0].license_commercial_ok if ledger_rows else None,
            dataset_version=dataset_version,
            curated_at=curated_at,
        )

    values = [r.normalised_value for r in included if r.normalised_value is not None]
    agg = aggregate_continuous(values, is_potency=is_potency)
    label = 1 if agg.aggregated_value <= blocker_threshold_nm else 0

    license_resolved = all(r.license_status == "resolved" for r in included)
    training_eligible = (not agg.is_discordant) and license_resolved
    exclusion_reason = None
    if agg.is_discordant:
        exclusion_reason = "discordant_gt_10x"
    elif not license_resolved:
        exclusion_reason = "unresolved_license"

    unit_resolution_rate = (sum(1 for r in candidates if r.unit_status == "resolved") / len(candidates)) if candidates else 1.0
    license_resolution_rate = (sum(1 for r in candidates if r.license_status == "resolved") / len(candidates)) if candidates else 1.0
    assay_context_coverage = sum(
        1 for r in included if r.assay_organism is not None or r.assay_paradigm_classification is not None
    ) / len(included)
    document_years = sorted({r.document_year for r in included if r.document_year})

    quality = compute_quality_score(
        structure_validity=1.0,
        unit_resolution_rate=unit_resolution_rate,
        license_resolution=license_resolution_rate,
        measurement_consistency=0.0 if agg.is_discordant else 1.0,
        duplicate_resolution=1.0,
        assay_context_coverage=assay_context_coverage,
        provenance_completeness=1.0 if document_years else 0.0,
    )

    return CuratedCompoundRow(
        compound_id=compound_id,
        inchikey_full=compound_id,
        canonical_smiles=canonical_smiles,
        standardized_smiles=standardized_smiles,
        bemis_murcko_scaffold=bemis_murcko_scaffold,
        molecular_formula=molecular_formula,
        n_source_measurements_total=len(ledger_rows),
        n_source_measurements_used=len(included),
        aggregated_ic50_nm=round(agg.aggregated_value, 4),
        aggregation_method=agg.method,
        value_spread_log10=agg.value_spread_log10,
        is_discordant=agg.is_discordant,
        conflict_status="discordant" if agg.is_discordant else "consistent",
        label=label,
        training_eligible=training_eligible,
        exclusion_reason=exclusion_reason,
        quality=quality,
        measurement_ids=";".join(r.measurement_id for r in included),
        source_chembl_ids=";".join(sorted({r.molecule_chembl_id for r in ledger_rows})),
        source_document_years=";".join(document_years),
        molecule_pref_names="",
        license_spdx=included[0].license_spdx,
        license_tier=included[0].license_tier,
        license_commercial_ok=included[0].license_commercial_ok,
        dataset_version=dataset_version,
        curated_at=curated_at,
    )
