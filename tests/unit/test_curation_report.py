"""Tests for the curation report builder.

The property that matters most: the funnel's arithmetic is internally
consistent — every raw record is accounted for in exactly one bucket, and
nothing is hidden. This mirrors the real reconciliation performed by hand
against ``build_dataset.py``'s own manifest counts during development
(148/97 discordant and 9589/5344 final counts matched exactly for hERG and
CYP3A4 respectively) — this test locks in the arithmetic property that
made that reconciliation possible in the first place, on a small synthetic
example.
"""

from __future__ import annotations

import dataclasses

import pytest

from drugsim_curation.curated_view import CuratedCompoundRow
from drugsim_curation.ledger import MeasurementLedgerRow
from drugsim_curation.quality_score import compute_quality_score
from drugsim_curation.report import build_curation_report

pytestmark = pytest.mark.unit


def _ledger_row(**overrides) -> MeasurementLedgerRow:
    defaults = dict(
        measurement_id="src:1",
        compound_id="COMPOUND-A",
        source_dataset_id="src",
        source_record_id="1",
        endpoint="test_endpoint",
        molecule_chembl_id="CHEMBL1",
        structure_status="valid",
        structure_error=None,
        original_value="10",
        original_unit="nM",
        original_relation="=",
        normalised_value=10.0,
        normalised_unit="nM",
        unit_status="resolved",
        conversion_method="identity_nm_passthrough",
        conversion_status="not_required",
        assay_chembl_id="A1",
        assay_type_raw="F",
        assay_organism="Homo sapiens",
        assay_cell_type=None,
        assay_tissue=None,
        assay_paradigm_classification="functional_electrophysiology",
        assay_confidence_score=9,
        assay_context_unavailable_fields="concentration;temperature;pH;exposure_duration;method",
        data_validity_comment="",
        document_chembl_id="D1",
        document_year="2020",
        license_spdx="CC-BY-SA-3.0",
        license_tier="red",
        license_commercial_ok=True,
        license_status="resolved",
        curation_status="included",
        exclusion_reason=None,
        conflict_status="consistent",
        transformation_version="v1",
        retrieved_at="2026-01-01",
        curated_at="2026-01-02T00:00:00+00:00",
    )
    defaults.update(overrides)
    return MeasurementLedgerRow(**defaults)


def _curated_compound(**overrides) -> CuratedCompoundRow:
    quality = compute_quality_score(
        structure_validity=1.0, unit_resolution_rate=1.0, license_resolution=1.0,
        measurement_consistency=1.0, duplicate_resolution=1.0, assay_context_coverage=1.0,
        provenance_completeness=1.0,
    )
    defaults = dict(
        compound_id="COMPOUND-A", inchikey_full="COMPOUND-A", canonical_smiles="CCO", standardized_smiles="CCO",
        bemis_murcko_scaffold="", molecular_formula="C2H6O", n_source_measurements_total=1,
        n_source_measurements_used=1, aggregated_ic50_nm=10.0, aggregation_method="single_value",
        value_spread_log10=0.0, is_discordant=False, conflict_status="consistent", label=1,
        training_eligible=True, exclusion_reason=None, quality=quality, measurement_ids="src:1",
        source_chembl_ids="CHEMBL1", source_document_years="2020", molecule_pref_names="",
        license_spdx="CC-BY-SA-3.0", license_tier="red", license_commercial_ok=True,
        dataset_version="v1", curated_at="2026-01-02T00:00:00+00:00",
    )
    defaults.update(overrides)
    return CuratedCompoundRow(**defaults)


class TestFunnelArithmeticIsConsistent:
    def test_raw_records_equals_sum_of_structure_buckets(self) -> None:
        rows = [
            _ledger_row(measurement_id="s:1"),
            _ledger_row(measurement_id="s:2", structure_status="invalid_quarantined", structure_error="err", compound_id="UNRESOLVED:X", curation_status="excluded", exclusion_reason="invalid_structure", conflict_status="not_applicable"),
            _ledger_row(measurement_id="s:3", structure_status="mixture_excluded", compound_id="UNRESOLVED:Y", curation_status="excluded", exclusion_reason="mixture", conflict_status="not_applicable"),
        ]
        report = build_curation_report(
            endpoint="test_endpoint", generated_at="2026-01-02", raw_csv_path="x.csv",
            raw_manifest_sha256="abc", retrieval_date="2026-01-01",
            ledger_rows=rows, curated_compounds=[_curated_compound()],
            ledger_output={"path": "a", "sha256": "b"}, curated_output={"path": "c", "sha256": "d"},
        )
        funnel = report["funnel"]
        assert funnel["raw_records"] == 3
        assert funnel["valid_structures"] + funnel["invalid_structures_quarantined"] + funnel["mixtures_excluded"] == 3

    def test_compound_funnel_sums_to_standardized_entities(self) -> None:
        compounds = [
            _curated_compound(compound_id="A", training_eligible=True, conflict_status="consistent"),
            _curated_compound(compound_id="B", training_eligible=False, conflict_status="discordant", exclusion_reason="discordant_gt_10x", is_discordant=True),
            _curated_compound(compound_id="C", training_eligible=False, conflict_status="insufficient_data", exclusion_reason="no_usable_measurements", n_source_measurements_used=0, label=None, aggregated_ic50_nm=None, measurement_ids=""),
        ]
        rows = [_ledger_row(measurement_id=f"s:{c.compound_id}", compound_id=c.compound_id) for c in compounds]
        report = build_curation_report(
            endpoint="test_endpoint", generated_at="2026-01-02", raw_csv_path="x.csv",
            raw_manifest_sha256="abc", retrieval_date="2026-01-01",
            ledger_rows=rows, curated_compounds=compounds,
            ledger_output={"path": "a", "sha256": "b"}, curated_output={"path": "c", "sha256": "d"},
        )
        funnel = report["funnel"]
        assert funnel["standardized_entities"] == 3
        assert funnel["training_eligible_compounds"] == 1
        assert funnel["training_ineligible_compounds"] == 2
        assert report["exclusion_reasons"]["compound_level"]["discordant_gt_10x"] == 1
        assert report["exclusion_reasons"]["compound_level"]["no_usable_measurements"] == 1


class TestNothingIsHidden:
    def test_every_excluded_measurement_reason_is_counted(self) -> None:
        rows = [
            _ledger_row(measurement_id="s:1", curation_status="excluded", exclusion_reason="censored_measurement", conflict_status="not_applicable"),
            _ledger_row(measurement_id="s:2", curation_status="excluded", exclusion_reason="censored_measurement", conflict_status="not_applicable"),
            _ledger_row(measurement_id="s:3", curation_status="excluded", exclusion_reason="unresolved_unit", conflict_status="not_applicable"),
        ]
        report = build_curation_report(
            endpoint="test_endpoint", generated_at="2026-01-02", raw_csv_path="x.csv",
            raw_manifest_sha256="abc", retrieval_date="2026-01-01",
            ledger_rows=rows, curated_compounds=[],
            ledger_output={"path": "a", "sha256": "b"}, curated_output={"path": "c", "sha256": "d"},
        )
        reasons = report["exclusion_reasons"]["measurement_level"]
        assert reasons["censored_measurement"] == 2
        assert reasons["unresolved_unit"] == 1
        assert sum(reasons.values()) == 3

    def test_empty_curated_compounds_reports_none_scores_not_a_crash(self) -> None:
        report = build_curation_report(
            endpoint="test_endpoint", generated_at="2026-01-02", raw_csv_path="x.csv",
            raw_manifest_sha256="abc", retrieval_date="2026-01-01",
            ledger_rows=[], curated_compounds=[],
            ledger_output={"path": "a", "sha256": "b"}, curated_output={"path": "c", "sha256": "d"},
        )
        assert report["quality_score_distribution"]["mean"] is None
        assert report["funnel"]["raw_records"] == 0


class TestExactDuplicatesAreCounted:
    def test_duplicate_role_is_reflected_in_the_funnel(self) -> None:
        rep = dataclasses.replace(_ledger_row(measurement_id="s:1"), duplicate_group_id="g1", duplicate_role="representative")
        dup = dataclasses.replace(_ledger_row(measurement_id="s:2"), duplicate_group_id="g1", duplicate_role="duplicate")
        report = build_curation_report(
            endpoint="test_endpoint", generated_at="2026-01-02", raw_csv_path="x.csv",
            raw_manifest_sha256="abc", retrieval_date="2026-01-01",
            ledger_rows=[rep, dup], curated_compounds=[],
            ledger_output={"path": "a", "sha256": "b"}, curated_output={"path": "c", "sha256": "d"},
        )
        assert report["funnel"]["exact_duplicate_records_collapsed"] == 1
