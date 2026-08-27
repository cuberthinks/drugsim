"""Tests for assay-context enrichment, offline (cache-only, no network).

``tests/integration/test_curation_assay_context_live.py`` covers the real
ChEMBL round-trip; this file covers everything that can be tested from a
pre-populated cache alone -- classification logic, the cache-hit path, and
that missing/uncached assays are simply absent from the result rather than
fabricated.
"""

from __future__ import annotations

import json

import pytest

from drugsim_curation.assay_context import (
    ASSAY_CONTEXT_UNAVAILABLE_FIELDS,
    classify_assay_paradigm,
    fetch_assay_metadata,
)

pytestmark = pytest.mark.unit


class TestParadigmClassification:
    def test_patch_clamp_is_functional_electrophysiology(self) -> None:
        assert classify_assay_paradigm("Whole-cell patch clamp assay for hERG current") == "functional_electrophysiology"

    def test_flipr_is_functional_flux(self) -> None:
        assert classify_assay_paradigm("FLIPR-based thallium flux assay") == "functional_flux_fluorescence"

    def test_radioligand_binding_is_binding_displacement(self) -> None:
        assert classify_assay_paradigm("[3H]dofetilide radioligand binding displacement") == "binding_displacement"

    def test_generic_inhibition_text_is_ambiguous(self) -> None:
        assert classify_assay_paradigm("Inhibition of target activity") == "ambiguous_generic_inhibition"

    def test_none_description_is_unclassified(self) -> None:
        assert classify_assay_paradigm(None) == "other_unclassified"

    def test_unrelated_text_is_unclassified(self) -> None:
        assert classify_assay_paradigm("Some unrelated assay description") == "other_unclassified"


class TestUnavailableFieldsAreDocumentedNotFabricated:
    def test_tissue_is_not_in_the_unavailable_list(self) -> None:
        # A real, verified finding during development: assay_tissue IS a
        # genuine ChEMBL field (sparsely populated, but real) -- it must
        # never be listed alongside fields that are structurally absent.
        assert "tissue" not in ASSAY_CONTEXT_UNAVAILABLE_FIELDS

    def test_concentration_and_temperature_are_documented_as_unavailable(self) -> None:
        assert "concentration" in ASSAY_CONTEXT_UNAVAILABLE_FIELDS
        assert "temperature" in ASSAY_CONTEXT_UNAVAILABLE_FIELDS


class TestCacheOnlyLookup:
    def test_cached_assay_is_resolved_with_no_network_call(self, tmp_path) -> None:
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(
            json.dumps(
                {
                    "CHEMBLA1": {
                        "assay_organism": "Homo sapiens",
                        "assay_cell_type": "HEK293",
                        "assay_tissue": None,
                        "confidence_score": 9,
                        "description": "Patch clamp hERG current",
                    }
                }
            ),
            encoding="utf-8",
        )
        result = fetch_assay_metadata("CHEMBL240", {"CHEMBLA1"}, cache_path=cache_path, http_client=None)
        assert result["CHEMBLA1"].assay_organism == "Homo sapiens"
        assert result["CHEMBLA1"].paradigm == "functional_electrophysiology"

    def test_uncached_assay_with_no_http_client_is_absent_not_fabricated(self, tmp_path) -> None:
        cache_path = tmp_path / "cache.json"
        result = fetch_assay_metadata("CHEMBL240", {"CHEMBL_NOT_CACHED"}, cache_path=cache_path, http_client=None)
        assert "CHEMBL_NOT_CACHED" not in result

    def test_missing_cache_file_starts_empty_not_an_error(self, tmp_path) -> None:
        cache_path = tmp_path / "does_not_exist.json"
        result = fetch_assay_metadata("CHEMBL240", {"CHEMBLA1"}, cache_path=cache_path, http_client=None)
        assert result == {}

    def test_real_sparse_tissue_value_is_carried_through_when_present(self, tmp_path) -> None:
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(
            json.dumps({"CHEMBLA2": {"assay_tissue": "liver", "description": "binding assay"}}), encoding="utf-8"
        )
        result = fetch_assay_metadata("CHEMBL240", {"CHEMBLA2"}, cache_path=cache_path, http_client=None)
        assert result["CHEMBLA2"].assay_tissue == "liver"
