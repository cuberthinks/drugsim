"""Constraint tests: chemistry domain.

TestScaffoldLeakagePrevention is the single most consequential test in this
suite: it proves that ADR-009's leakage guarantee is a database-level
impossibility, not a pipeline convention that a future ETL bug could quietly
violate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drugsim_core.ids import generate_ulid

from .factories import insert_compound, insert_data_source, insert_ingestion_snapshot, insert_toolchain

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


@pytest.fixture
def base_fixtures(session: Session, curator_user_id: str) -> dict[str, str]:
    """Common FK targets needed by nearly every compound-domain test."""
    source_id = insert_data_source(session)
    snapshot_id = insert_ingestion_snapshot(session, source_id)
    toolchain_id = insert_toolchain(session)
    session.flush()
    return {
        "source_id": source_id,
        "snapshot_id": snapshot_id,
        "toolchain_id": toolchain_id,
        "created_by": curator_user_id,
    }


class TestCompoundIdentity:
    """uq_compound_inchikey, ck_skeleton_prefix, ck_deleted_reason, ck_mixture_no_parent."""

    def test_duplicate_inchikey_rejected(self, session: Session, base_fixtures: dict[str, str]) -> None:
        ik = "AAAAAAAAAAAAAA-BBBBBBBBBB-C"
        insert_compound(session, inchikey_full=ik, **base_fixtures)
        session.flush()
        with pytest.raises(IntegrityError, match="uq_compound_inchikey"):
            insert_compound(session, inchikey_full=ik, compound_uid=generate_ulid(), **base_fixtures)
            session.flush()

    def test_skeleton_must_match_full_key_prefix(self, session: Session, base_fixtures: dict[str, str]) -> None:
        """Direct-SQL attempt to violate ck_skeleton_prefix, bypassing the factory."""
        with pytest.raises(IntegrityError, match="ck_skeleton_prefix"):
            session.execute(
                text(
                    "INSERT INTO compound (compound_uid, source_smiles, canonical_smiles, "
                    "isomeric_smiles, standardized_smiles, inchi, inchikey_full, "
                    "inchikey_skeleton, molecular_formula, stereo_completeness, mol, "
                    "morgan_fp_r2_2048, source_id, snapshot_id, source_license, "
                    "license_tier, is_commercial_ok, toolchain_id, pipeline_version, "
                    "drugsim_release, created_by) "
                    "VALUES (:uid, 'CCO', 'CCO', 'CCO', 'CCO', 'InChI=1S/x', "
                    "'AAAAAAAAAAAAAA-BBBBBBBBBB-C', 'WRONGWRONGWR', 'C2H6O', "
                    "'not_applicable', mol_from_smiles('CCO'), "
                    "morganbv_fp(mol_from_smiles('CCO'), 2), :source_id, :snapshot_id, "
                    "'CC-BY-4.0', 'amber', true, :toolchain_id, :pv, '0.1.0', :created_by)"
                ),
                {
                    "uid": generate_ulid(),
                    "source_id": base_fixtures["source_id"],
                    "snapshot_id": base_fixtures["snapshot_id"],
                    "toolchain_id": base_fixtures["toolchain_id"],
                    "pv": "d" * 40,
                    "created_by": base_fixtures["created_by"],
                },
            )
            session.flush()

    def test_deleted_requires_reason(self, session: Session, base_fixtures: dict[str, str]) -> None:
        with pytest.raises(IntegrityError, match="ck_deleted_reason"):
            insert_compound(session, is_deleted=True, deleted_reason=None, **base_fixtures)
            session.flush()

    def test_deleted_with_reason_succeeds(self, session: Session, base_fixtures: dict[str, str]) -> None:
        insert_compound(session, is_deleted=True, deleted_reason="duplicate of X", **base_fixtures)
        session.flush()

    def test_mixture_cannot_have_parent_inchikey(self, session: Session, base_fixtures: dict[str, str]) -> None:
        """A genuine mixture has no clear parent (Phase 1 Step 4 §2.2)."""
        with pytest.raises(IntegrityError, match="ck_mixture_no_parent"):
            insert_compound(
                session,
                is_mixture=True,
                parent_inchikey="DDDDDDDDDDDDDD-EEEEEEEEEE-F",
                **base_fixtures,
            )
            session.flush()

    def test_non_mixture_with_parent_succeeds(self, session: Session, base_fixtures: dict[str, str]) -> None:
        insert_compound(
            session, is_mixture=False, parent_inchikey="DDDDDDDDDDDDDD-EEEEEEEEEE-F", **base_fixtures
        )
        session.flush()


class TestDescriptorConsistency:
    """ck_mass_consistency: monoisotopic and average mass never diverge by >=0.5 Da
    for drug-like molecules — catches unit and parsing errors early."""

    def test_grossly_inconsistent_masses_rejected(
        self, session: Session, base_fixtures: dict[str, str]
    ) -> None:
        from .factories import insert_descriptor_spec

        compound_uid = insert_compound(session, **base_fixtures)
        descriptor_spec_version = insert_descriptor_spec(session, base_fixtures["toolchain_id"])
        session.flush()

        with pytest.raises(IntegrityError, match="ck_mass_consistency"):
            session.execute(
                text(
                    "INSERT INTO compound_descriptor (compound_uid, descriptor_spec_version, "
                    "mw_g_mol, exact_mass_g_mol, logp_crippen, tpsa_a2, rotatable_bonds, "
                    "aromatic_rings, ring_count, heavy_atom_count, formal_charge, "
                    "hbd_lipinski, hba_lipinski, hbd_strict, hba_strict, "
                    "heteroatom_count, fraction_csp3, num_stereocentres) "
                    "VALUES (:cuid, :dsv, 46.07, 100.00, 0.1, 20.2, 1, 0, 0, 3, 0, "
                    "1, 1, 1, 1, 1, 0.5, 0)"
                ),
                {"cuid": compound_uid, "dsv": descriptor_spec_version},
            )
            session.flush()


class TestScaffoldLeakagePrevention:
    """uq_scaffold_single_group: the ADR-009 leakage guarantee, as a constraint.

    Cross-dataset leakage was Phase 1's central risk for the small ADMET
    datasets (475-13,130 compounds). If a scaffold could sit in two split
    groups, a scaffold in Caco-2 train and DILI test would leak through any
    multi-task model or shared encoder. This makes that impossible rather than
    merely discouraged by pipeline convention.
    """

    def test_same_scaffold_two_groups_rejected(
        self, session: Session, base_fixtures: dict[str, str]
    ) -> None:
        scaffold = "c1ccccc1"  # benzene
        cid1 = insert_compound(session, compound_uid=generate_ulid(), **base_fixtures)
        cid2 = insert_compound(session, compound_uid=generate_ulid(), **base_fixtures)
        session.flush()

        session.execute(
            text(
                "INSERT INTO compound_split_assignment (compound_uid, scaffold_key, "
                "split_group, split_salt, assigned_in_release) "
                "VALUES (:cid, :scaffold, 0, 'salt1', '0.1.0')"
            ),
            {"cid": cid1, "scaffold": scaffold},
        )
        session.flush()

        with pytest.raises(IntegrityError, match="uq_scaffold_single_group"):
            session.execute(
                text(
                    "INSERT INTO compound_split_assignment (compound_uid, scaffold_key, "
                    "split_group, split_salt, assigned_in_release) "
                    "VALUES (:cid, :scaffold, 1, 'salt1', '0.1.0')"
                ),
                {"cid": cid2, "scaffold": scaffold},
            )
            session.flush()

    def test_same_scaffold_same_group_twice_is_fine_via_different_compounds(
        self, session: Session, base_fixtures: dict[str, str]
    ) -> None:
        """Two different compounds sharing a scaffold and a split group is expected
        and correct — the constraint only forbids the SAME scaffold spanning
        DIFFERENT groups."""
        scaffold = "c1ccncc1"
        cid1 = insert_compound(session, compound_uid=generate_ulid(), **base_fixtures)
        cid2 = insert_compound(session, compound_uid=generate_ulid(), **base_fixtures)
        session.flush()

        for cid in (cid1, cid2):
            session.execute(
                text(
                    "INSERT INTO compound_split_assignment (compound_uid, scaffold_key, "
                    "split_group, split_salt, assigned_in_release) "
                    "VALUES (:cid, :scaffold, 3, 'salt1', '0.1.0')"
                ),
                {"cid": cid, "scaffold": scaffold},
            )
        session.flush()  # must not raise

    def test_split_group_out_of_range_rejected(
        self, session: Session, base_fixtures: dict[str, str]
    ) -> None:
        cid = insert_compound(session, **base_fixtures)
        session.flush()
        with pytest.raises(IntegrityError):
            session.execute(
                text(
                    "INSERT INTO compound_split_assignment (compound_uid, scaffold_key, "
                    "split_group, split_salt, assigned_in_release) "
                    "VALUES (:cid, 'x', 10, 'salt', '0.1.0')"
                ),
                {"cid": cid},
            )
            session.flush()
