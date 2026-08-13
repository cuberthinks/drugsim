"""Integration test: bulk loading real processed compounds against a real schema.

The row-building logic (drugsim_db.bulk_load.build_*) is unit-tested directly in
tests/unit/test_bulk_load.py with no database at all. This file covers only what
that cannot: that the generated INSERTs (including the mol_from_smiles/morganbv_fp
cartridge calls) actually execute against the real schema, that the composite FK
from compound_drug_likeness to compound_descriptor holds, and that a mixture
correctly lands a compound row with no descriptor/drug-likeness rows.

Requires Docker (testcontainers) — not executed in this environment (no Docker
available); written and reviewed for correctness, to be run in CI where the
Postgres+RDKit service is available. See docs/phase2/phase2-completion-report.md.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_chem import DESCRIPTOR_SPEC_VERSION, STANDARDIZATION_PIPELINE_VERSION, process_structure
from drugsim_core.version import get_rdkit_version
from drugsim_db.audit import audit_context
from drugsim_db.bulk_load import (
    CompoundProvenance,
    ensure_descriptor_spec,
    ensure_toolchain,
    load_compounds,
)
from drugsim_features import compute_feature_set_id

from .factories import insert_data_source, insert_ingestion_snapshot

pytestmark = [pytest.mark.integration, pytest.mark.constraints]

_DESCRIPTOR_NAMES = [
    "mw_g_mol",
    "mw_parent_g_mol",
    "exact_mass_g_mol",
    "logp_crippen",
    "molar_refractivity",
    "tpsa_a2",
    "rotatable_bonds",
    "aromatic_rings",
    "ring_count",
    "heavy_atom_count",
    "formal_charge",
    "hbd_lipinski",
    "hba_lipinski",
    "hbd_strict",
    "hba_strict",
    "heteroatom_count",
    "fraction_csp3",
    "num_stereocentres",
    "largest_ring_size",
]


@pytest.fixture
def provenance(session: Session, curator_user_id: str) -> CompoundProvenance:
    source_id = insert_data_source(session)
    snapshot_id = insert_ingestion_snapshot(session, source_id)
    toolchain_id = f"rdkit-{get_rdkit_version()}__stdpipe-{STANDARDIZATION_PIPELINE_VERSION}"
    ensure_toolchain(
        session,
        toolchain_id=toolchain_id,
        rdkit_version=str(get_rdkit_version()),
        python_version="3.12.4",
        std_pipeline_ver=STANDARDIZATION_PIPELINE_VERSION,
    )
    feature_set_id = compute_feature_set_id(
        descriptor_spec_version=DESCRIPTOR_SPEC_VERSION,
        rdkit_version=str(get_rdkit_version()),
        standardization_pipeline_version=STANDARDIZATION_PIPELINE_VERSION,
        descriptor_names=_DESCRIPTOR_NAMES,
    )
    ensure_descriptor_spec(
        session,
        descriptor_spec_version=DESCRIPTOR_SPEC_VERSION,
        toolchain_id=toolchain_id,
        feature_set_id=feature_set_id,
        descriptor_list=_DESCRIPTOR_NAMES,
    )
    session.flush()
    return CompoundProvenance(
        source_id=source_id,
        snapshot_id=snapshot_id,
        source_license="CC-BY-4.0",
        license_tier="amber",
        is_commercial_ok=True,
        toolchain_id=toolchain_id,
        descriptor_spec_version=DESCRIPTOR_SPEC_VERSION,
        pipeline_version="a" * 40,
        drugsim_release="0.1.0",
        created_by=curator_user_id,
    )


class TestLoadCompoundsAgainstRealSchema:
    def test_ordinary_compound_loads_all_three_rows(
        self, session: Session, provenance: CompoundProvenance, curator_user_id: str
    ) -> None:
        processed = [process_structure("CC(=O)Oc1ccccc1C(=O)O")]  # aspirin
        with audit_context(session, user_id=curator_user_id, reason="test bulk load"):
            result = load_compounds(session, processed, provenance)
        session.flush()

        assert result.compounds_loaded == 1
        assert result.descriptors_loaded == 1
        assert result.drug_likeness_loaded == 1

        row = session.execute(
            text("SELECT inchikey_full, molecular_formula FROM compound")
        ).mappings().one()
        assert row["inchikey_full"] == processed[0].identity.inchikey_full
        assert row["molecular_formula"] == processed[0].identity.molecular_formula

    def test_mixture_loads_compound_row_only(
        self, session: Session, provenance: CompoundProvenance, curator_user_id: str
    ) -> None:
        processed = [process_structure("CCO.CCN")]
        with audit_context(session, user_id=curator_user_id, reason="test bulk load"):
            result = load_compounds(session, processed, provenance)
        session.flush()

        assert result.compounds_loaded == 1
        assert result.descriptors_loaded == 0
        assert result.drug_likeness_loaded == 0
        assert result.mixtures_without_descriptors == 1

        count = session.execute(text("SELECT count(*) FROM compound_descriptor")).scalar_one()
        assert count == 0

    def test_whole_salt_loads_with_null_parent_fields(
        self, session: Session, provenance: CompoundProvenance, curator_user_id: str
    ) -> None:
        """Regression coverage at the schema level for the standardize.py
        parent_mol bugfix: a whole-salt compound must persist with NULL
        parent_smiles/parent_inchikey and NULL mw_parent_g_mol."""
        processed = [process_structure("[Na+].[Cl-]")]
        with audit_context(session, user_id=curator_user_id, reason="test bulk load"):
            load_compounds(session, processed, provenance)
        session.flush()

        row = session.execute(
            text("SELECT parent_smiles, parent_inchikey FROM compound")
        ).mappings().one()
        assert row["parent_smiles"] is None
        assert row["parent_inchikey"] is None

        desc_row = session.execute(
            text("SELECT mw_parent_g_mol FROM compound_descriptor")
        ).mappings().one()
        assert desc_row["mw_parent_g_mol"] is None

    def test_batch_of_several_compounds(
        self, session: Session, provenance: CompoundProvenance, curator_user_id: str
    ) -> None:
        smiles = ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "c1ccccc1", "CCN(CC)CC.Cl"]
        processed = [process_structure(s) for s in smiles]
        with audit_context(session, user_id=curator_user_id, reason="test batch load"):
            result = load_compounds(session, processed, provenance)
        session.flush()

        assert result.compounds_loaded == len(smiles)
        count = session.execute(text("SELECT count(*) FROM compound")).scalar_one()
        assert count == len(smiles)

    def test_created_by_and_toolchain_recorded(
        self, session: Session, provenance: CompoundProvenance, curator_user_id: str
    ) -> None:
        processed = [process_structure("CCO")]
        with audit_context(session, user_id=curator_user_id, reason="test bulk load"):
            load_compounds(session, processed, provenance)
        session.flush()

        row = session.execute(
            text("SELECT created_by, toolchain_id FROM compound")
        ).mappings().one()
        assert row["created_by"] == curator_user_id
        assert row["toolchain_id"] == provenance.toolchain_id
