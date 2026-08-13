"""Tests for duplicate detection."""

from __future__ import annotations

import pytest

from drugsim_quality.dedup import MeasurementRecord, find_compound_duplicates, find_measurement_duplicates

pytestmark = pytest.mark.unit


class TestCompoundDuplicates:
    def test_singleton_is_not_a_duplicate(self) -> None:
        groups = find_compound_duplicates([("c1", "IKEY1")])
        assert groups == []

    def test_two_records_same_inchikey_grouped(self) -> None:
        groups = find_compound_duplicates([("c1", "IKEY1"), ("c2", "IKEY1")])
        assert len(groups) == 1
        assert set(groups[0].record_ids) == {"c1", "c2"}

    def test_first_seen_is_representative(self) -> None:
        groups = find_compound_duplicates([("c1", "IKEY1"), ("c2", "IKEY1")])
        assert groups[0].representative_id == "c1"

    def test_different_keys_not_grouped(self) -> None:
        groups = find_compound_duplicates([("c1", "IKEY1"), ("c2", "IKEY2")])
        assert groups == []

    def test_no_records_lost_across_multiple_groups(self) -> None:
        records = [("c1", "A"), ("c2", "A"), ("c3", "B"), ("c4", "B"), ("c5", "C")]
        groups = find_compound_duplicates(records)
        all_grouped = {rid for g in groups for rid in g.record_ids}
        assert all_grouped == {"c1", "c2", "c3", "c4"}  # c5 is a singleton, correctly excluded


class TestMeasurementDuplicatesWithReference:
    def test_shared_reference_and_target_groups(self) -> None:
        records = [
            MeasurementRecord("m1", "IKEY1", "CHEMBL203", reference="10.1000/x"),
            MeasurementRecord("m2", "IKEY1", "CHEMBL203", reference="10.1000/x"),
        ]
        groups = find_measurement_duplicates(records)
        assert len(groups) == 1
        assert set(groups[0].record_ids) == {"m1", "m2"}

    def test_different_reference_not_grouped(self) -> None:
        records = [
            MeasurementRecord("m1", "IKEY1", "CHEMBL203", reference="10.1000/x"),
            MeasurementRecord("m2", "IKEY1", "CHEMBL203", reference="10.1000/y"),
        ]
        assert find_measurement_duplicates(records) == []

    def test_different_target_not_grouped_even_with_same_reference(self) -> None:
        records = [
            MeasurementRecord("m1", "IKEY1", "CHEMBL203", reference="10.1000/x"),
            MeasurementRecord("m2", "IKEY1", "CHEMBL204", reference="10.1000/x"),
        ]
        assert find_measurement_duplicates(records) == []


class TestMeasurementDuplicatesWithoutReference:
    """Weaker signal (structure+target only), still catches the bulk of the
    ChEMBL/BindingDB overlap Phase 1 identified as substantial."""

    def test_same_compound_and_target_no_reference_grouped(self) -> None:
        records = [
            MeasurementRecord("m1", "IKEY1", "CHEMBL203"),
            MeasurementRecord("m2", "IKEY1", "CHEMBL203"),
        ]
        groups = find_measurement_duplicates(records)
        assert len(groups) == 1


class TestRepresentativeSelection:
    """Least-restrictive licence tier wins — a free reduction in ShareAlike
    exposure when the underlying values are identical (Phase 1 Step 8 §8.2)."""

    def test_amber_beats_red_as_representative(self) -> None:
        records = [
            MeasurementRecord("m_red", "IKEY1", "CHEMBL203", license_tier="red", confidence_score=0.9),
            MeasurementRecord("m_amber", "IKEY1", "CHEMBL203", license_tier="amber", confidence_score=0.5),
        ]
        groups = find_measurement_duplicates(records)
        assert groups[0].representative_id == "m_amber"

    def test_green_beats_everything(self) -> None:
        records = [
            MeasurementRecord("m_red", "IKEY1", "CHEMBL203", license_tier="red"),
            MeasurementRecord("m_green", "IKEY1", "CHEMBL203", license_tier="green"),
            MeasurementRecord("m_amber", "IKEY1", "CHEMBL203", license_tier="amber"),
        ]
        groups = find_measurement_duplicates(records)
        assert groups[0].representative_id == "m_green"

    def test_same_tier_breaks_tie_by_confidence(self) -> None:
        records = [
            MeasurementRecord("m_low", "IKEY1", "CHEMBL203", license_tier="amber", confidence_score=0.3),
            MeasurementRecord("m_high", "IKEY1", "CHEMBL203", license_tier="amber", confidence_score=0.9),
        ]
        groups = find_measurement_duplicates(records)
        assert groups[0].representative_id == "m_high"

    def test_no_record_is_discarded_only_grouped(self) -> None:
        """P8: deduplication groups records, it never deletes one."""
        records = [
            MeasurementRecord("m1", "IKEY1", "CHEMBL203", license_tier="red"),
            MeasurementRecord("m2", "IKEY1", "CHEMBL203", license_tier="amber"),
        ]
        groups = find_measurement_duplicates(records)
        assert set(groups[0].record_ids) == {"m1", "m2"}
