"""Unit tests for the pure row-building side of the bulk loader.

No database needed here — these exercise build_compound_row/build_descriptor_row/
build_drug_likeness_row/build_rows against real process_structure() output, the
same pure/thin split already used by registry_sync and snapshots.
"""

from __future__ import annotations

import pytest

from drugsim_chem import process_structure
from drugsim_db.bulk_load import (
    CompoundProvenance,
    build_compound_row,
    build_descriptor_row,
    build_drug_likeness_row,
    build_rows,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def provenance() -> CompoundProvenance:
    return CompoundProvenance(
        source_id="test_source",
        snapshot_id="snap_test",
        source_license="CC-BY-4.0",
        license_tier="amber",
        is_commercial_ok=True,
        toolchain_id="test-toolchain",
        descriptor_spec_version="v1",
        pipeline_version="a" * 40,
        drugsim_release="0.1.0",
        created_by="0" * 26,
    )


class TestBuildCompoundRow:
    def test_ordinary_compound_row_shape(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO")
        row = build_compound_row(processed, provenance)
        assert row["source_smiles"] == "CCO"
        assert row["canonical_smiles"] == processed.identity.canonical_smiles
        assert row["inchikey_full"] == processed.identity.inchikey_full
        assert row["inchikey_skeleton"] == processed.identity.inchikey_skeleton
        assert row["molecular_formula"] == processed.identity.molecular_formula
        assert row["is_mixture"] is False
        assert row["component_count"] == 1
        assert len(row["compound_uid"]) == 26

    def test_compound_uid_is_generated_when_omitted(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO")
        row_a = build_compound_row(processed, provenance)
        row_b = build_compound_row(processed, provenance)
        assert row_a["compound_uid"] != row_b["compound_uid"]

    def test_compound_uid_can_be_supplied(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO")
        row = build_compound_row(processed, provenance, compound_uid="A" * 26)
        assert row["compound_uid"] == "A" * 26

    def test_source_record_id_passed_through(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO")
        row = build_compound_row(processed, provenance, source_record_id="CHEMBL25")
        assert row["source_record_id"] == "CHEMBL25"

    def test_provenance_fields_copied_verbatim(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO")
        row = build_compound_row(processed, provenance)
        assert row["source_id"] == provenance.source_id
        assert row["snapshot_id"] == provenance.snapshot_id
        assert row["source_license"] == provenance.source_license
        assert row["license_tier"] == provenance.license_tier
        assert row["is_commercial_ok"] == provenance.is_commercial_ok
        assert row["toolchain_id"] == provenance.toolchain_id
        assert row["pipeline_version"] == provenance.pipeline_version
        assert row["drugsim_release"] == provenance.drugsim_release
        assert row["created_by"] == provenance.created_by

    def test_parent_inchikey_set_when_parent_identified(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCN(CC)CC.Cl")  # triethylamine hydrochloride
        row = build_compound_row(processed, provenance)
        assert row["parent_smiles"] is not None
        assert row["parent_inchikey"] == processed.identity.inchikey_full

    def test_parent_inchikey_none_for_whole_salt(self, provenance: CompoundProvenance) -> None:
        """Regression coverage for the standardize.py parent_mol bugfix:
        a whole-salt structure has no identified organic parent, so
        parent_inchikey (and parent_smiles) must be None, not populated."""
        processed = process_structure("[Na+].[Cl-]")
        row = build_compound_row(processed, provenance)
        assert row["parent_smiles"] is None
        assert row["parent_inchikey"] is None

    def test_parent_inchikey_none_for_mixture(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO.CCN")
        row = build_compound_row(processed, provenance)
        assert row["is_mixture"] is True
        assert row["parent_smiles"] is None
        assert row["parent_inchikey"] is None


class TestBuildDescriptorRow:
    def test_ordinary_compound_has_descriptor_row(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CC(=O)Oc1ccccc1C(=O)O")  # aspirin
        row = build_descriptor_row("A" * 26, processed, provenance)
        assert row is not None
        assert row["compound_uid"] == "A" * 26
        assert row["descriptor_spec_version"] == "v1"
        assert row["mw_g_mol"] == processed.descriptors.mw_g_mol

    def test_mixture_has_no_descriptor_row(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO.CCN")
        row = build_descriptor_row("A" * 26, processed, provenance)
        assert row is None

    def test_whole_salt_has_null_mw_parent(self, provenance: CompoundProvenance) -> None:
        """Regression coverage: mw_parent_g_mol must be None for a
        whole-salt structure, not the salt's own mass."""
        processed = process_structure("[Na+].[Cl-]")
        row = build_descriptor_row("A" * 26, processed, provenance)
        assert row is not None
        assert row["mw_parent_g_mol"] is None


class TestBuildDrugLikenessRow:
    def test_ordinary_compound_has_drug_likeness_row(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CC(=O)Oc1ccccc1C(=O)O")
        row = build_drug_likeness_row("A" * 26, processed, provenance)
        assert row is not None
        assert row["lipinski_pass"] == processed.drug_likeness.lipinski_pass
        assert row["gsk_4_400_flag"] == processed.drug_likeness.gsk_4_400_flag

    def test_pfizer_flag_none_without_logd(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CC(=O)Oc1ccccc1C(=O)O")
        row = build_drug_likeness_row("A" * 26, processed, provenance)
        assert row is not None
        assert row["pfizer_3_75_flag"] is None

    def test_mixture_has_no_drug_likeness_row(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO.CCN")
        row = build_drug_likeness_row("A" * 26, processed, provenance)
        assert row is None


class TestBuildRows:
    def test_all_three_rows_share_the_same_compound_uid(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CC(=O)Oc1ccccc1C(=O)O")
        rows = build_rows(processed, provenance)
        assert rows.descriptor is not None
        assert rows.drug_likeness is not None
        uid = rows.compound["compound_uid"]
        assert rows.descriptor["compound_uid"] == uid
        assert rows.drug_likeness["compound_uid"] == uid

    def test_mixture_yields_compound_row_only(self, provenance: CompoundProvenance) -> None:
        processed = process_structure("CCO.CCN")
        rows = build_rows(processed, provenance)
        assert rows.compound is not None
        assert rows.descriptor is None
        assert rows.drug_likeness is None
