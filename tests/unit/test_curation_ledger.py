"""Tests for the per-measurement curation ledger.

The properties that matter most: (1) every raw row produces a ledger row,
including the ones a live pipeline would drop -- nothing silently
disappears; (2) `measurement_id`/`compound_id` are deterministic, not
random, so the same raw input always produces the same ledger; (3)
exclusion reasons follow a documented priority so a row failing multiple
checks reports the most fundamental one.
"""

from __future__ import annotations

import pytest

from drugsim_curation.assay_context import AssayMetadata
from drugsim_curation.ledger import build_ledger_row, find_exact_duplicate_measurements
from drugsim_curation.provenance import LicenseResolution
from drugsim_curation.units import UnitResolution

pytestmark = pytest.mark.unit

_RESOLVED_LICENSE = LicenseResolution(
    source_id="chembl", spdx="CC-BY-SA-3.0", tier="red", commercial_ok=True, attribution="ChEMBL", license_status="resolved"
)
_UNRESOLVED_LICENSE = LicenseResolution(
    source_id="unknown", spdx=None, tier=None, commercial_ok=None, attribution=None, license_status="unresolved", reason="not found"
)
_RESOLVED_UNIT = UnitResolution(
    original_value="12.5", original_unit="nM", normalised_value=12.5, normalised_unit="nM",
    conversion_method="identity_nm_passthrough", conversion_status="not_required", unit_status="resolved",
)
_UNRESOLVED_UNIT = UnitResolution(
    original_value="5", original_unit="ug/mL", normalised_value=None, normalised_unit=None,
    conversion_method="no molecular weight", conversion_status="unresolved_no_molecular_weight", unit_status="unresolved",
)


def _raw_row(**overrides: str) -> dict[str, str]:
    row = {
        "activity_id": "1001",
        "molecule_chembl_id": "CHEMBL999",
        "canonical_smiles": "CCO",
        "standard_value": "12.5",
        "standard_units": "nM",
        "standard_relation": "=",
        "assay_type": "F",
        "assay_chembl_id": "CHEMBLA1",
        "data_validity_comment": "",
        "document_chembl_id": "CHEMBLD1",
        "document_year": "2020",
    }
    row.update(overrides)
    return row


def _build(**kwargs):
    defaults = dict(
        raw_row=_raw_row(),
        source_dataset_id="chembl_test_raw",
        endpoint="test_endpoint",
        structure_status="valid",
        structure_error=None,
        compound_id="ABCDEFGHIJKLMN-UHFFFAOYSA-N",
        unit_resolution=_RESOLVED_UNIT,
        assay_metadata=None,
        license_resolution=_RESOLVED_LICENSE,
        bad_validity_flags=frozenset({"Potential transcription error", "Potential author error"}),
        retrieved_at="2026-01-01",
        curated_at="2026-01-02T00:00:00+00:00",
    )
    defaults.update(kwargs)
    return build_ledger_row(**defaults)


class TestDeterministicIdentifiers:
    def test_measurement_id_is_deterministic_not_random(self) -> None:
        row_a = _build()
        row_b = _build()
        assert row_a.measurement_id == row_b.measurement_id == "chembl_test_raw:1001"

    def test_unresolved_structure_gets_a_deterministic_placeholder_compound_id(self) -> None:
        row = _build(structure_status="invalid_quarantined", structure_error="bad smiles", compound_id=None)
        assert row.compound_id == "UNRESOLVED:CHEMBL999"


class TestNothingIsSilentlyDropped:
    def test_a_censored_row_still_produces_a_ledger_row(self) -> None:
        row = _build(raw_row=_raw_row(standard_relation=">"))
        assert row.curation_status == "excluded"
        assert row.exclusion_reason == "censored_measurement"
        # The row exists and records what it was, even though it's excluded.
        assert row.original_value == "12.5"
        assert row.original_relation == ">"

    def test_an_invalid_structure_still_produces_a_ledger_row(self) -> None:
        row = _build(structure_status="invalid_quarantined", structure_error="kekulization failed", compound_id=None)
        assert row.curation_status == "excluded"
        assert row.exclusion_reason == "invalid_structure"
        assert row.structure_error == "kekulization failed"


class TestExclusionPriority:
    """A row failing multiple checks reports the most fundamental one."""

    def test_invalid_structure_beats_censored_and_unit(self) -> None:
        row = _build(
            structure_status="invalid_quarantined",
            structure_error="err",
            compound_id=None,
            raw_row=_raw_row(standard_relation=">"),
            unit_resolution=_UNRESOLVED_UNIT,
        )
        assert row.exclusion_reason == "invalid_structure"

    def test_mixture_beats_censored(self) -> None:
        row = _build(structure_status="mixture_excluded", raw_row=_raw_row(standard_relation=">"))
        assert row.exclusion_reason == "mixture"

    def test_censored_beats_bad_validity_and_unit(self) -> None:
        row = _build(
            raw_row=_raw_row(standard_relation=">", data_validity_comment="Potential author error"),
            unit_resolution=_UNRESOLVED_UNIT,
        )
        assert row.exclusion_reason == "censored_measurement"

    def test_bad_validity_beats_unresolved_unit(self) -> None:
        row = _build(
            raw_row=_raw_row(data_validity_comment="Potential author error"),
            unit_resolution=_UNRESOLVED_UNIT,
        )
        assert row.exclusion_reason == "bad_validity_comment"

    def test_unresolved_unit_beats_unresolved_license(self) -> None:
        row = _build(unit_resolution=_UNRESOLVED_UNIT, license_resolution=_UNRESOLVED_LICENSE)
        assert row.exclusion_reason == "unresolved_unit"

    def test_a_clean_row_is_included_with_no_exclusion_reason(self) -> None:
        row = _build()
        assert row.curation_status == "included"
        assert row.exclusion_reason is None


class TestEndpointSpecificBadValidityFlags:
    """hERG and CYP3A4's live pipelines use genuinely different flag sets."""

    def test_a_flag_only_cyp3a4_treats_as_bad_is_not_excluded_under_hergs_flags(self) -> None:
        herg_flags = frozenset({"Potential transcription error", "Potential author error"})
        row = _build(raw_row=_raw_row(data_validity_comment="Outside typical range"), bad_validity_flags=herg_flags)
        assert row.curation_status == "included"

    def test_the_same_flag_is_excluded_under_cyp3a4s_flags(self) -> None:
        cyp_flags = frozenset({"Potential transcription error", "Potential author error", "Outside typical range"})
        row = _build(raw_row=_raw_row(data_validity_comment="Outside typical range"), bad_validity_flags=cyp_flags)
        assert row.exclusion_reason == "bad_validity_comment"


class TestAssayContextNeverFabricated:
    def test_no_assay_metadata_means_null_fields_not_invented_ones(self) -> None:
        row = _build(assay_metadata=None)
        assert row.assay_organism is None
        assert row.assay_cell_type is None
        assert row.assay_paradigm_classification is None

    def test_real_assay_metadata_is_carried_through(self) -> None:
        metadata = AssayMetadata(
            assay_chembl_id="CHEMBLA1", assay_organism="Homo sapiens", assay_cell_type="HEK293",
            assay_tissue=None, confidence_score=9, paradigm="functional_electrophysiology",
        )
        row = _build(assay_metadata=metadata)
        assert row.assay_organism == "Homo sapiens"
        assert row.assay_paradigm_classification == "functional_electrophysiology"


class TestExactDuplicateDetection:
    def test_two_identical_rows_are_tagged_as_duplicates(self) -> None:
        row_a = _build(raw_row=_raw_row(activity_id="1"))
        row_b = _build(raw_row=_raw_row(activity_id="2"))  # same value/unit/relation/assay/document
        patched = find_exact_duplicate_measurements([row_a, row_b])
        assert len(patched) == 2
        roles = {patched[r.measurement_id].duplicate_role for r in (row_a, row_b)}
        assert roles == {"representative", "duplicate"}

    def test_a_different_value_is_not_a_duplicate(self) -> None:
        row_a = _build(raw_row=_raw_row(activity_id="1", standard_value="12.5"))
        row_b = _build(raw_row=_raw_row(activity_id="2", standard_value="99.0"))
        patched = find_exact_duplicate_measurements([row_a, row_b])
        assert patched == {}

    def test_a_singleton_row_is_never_tagged(self) -> None:
        row = _build()
        assert find_exact_duplicate_measurements([row]) == {}
