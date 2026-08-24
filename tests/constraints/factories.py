"""Minimal valid rows for constraint tests.

Each factory inserts the smallest set of columns needed to satisfy every NOT NULL
and FK requirement for one entity, so an individual test can violate exactly the
one constraint under examination without also having to reason about every other
constraint on the table. Values are otherwise arbitrary — these are fixtures, not
scientifically meaningful data.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_core.ids import generate_ulid

__all__ = [
    "fake_ulid",
    "insert_assay",
    "insert_compound",
    "insert_data_source",
    "insert_descriptor_spec",
    "insert_endpoint",
    "insert_ingestion_snapshot",
    "insert_model",
    "insert_model_version",
    "insert_organism",
    "insert_prediction",
    "insert_protein",
    "insert_target",
    "insert_toolchain",
]


def insert_data_source(
    session: Session,
    source_id: str = "test_source",
    *,
    tier: str = "amber",
    commercial_ok: bool = True,
    sharealike: bool = False,
) -> str:
    """Insert a minimal data_source row and return its id."""
    session.execute(
        text(
            "INSERT INTO data_source (source_id, name, homepage, role, license_spdx, "
            "license_tier, is_commercial_ok, has_sharealike, attribution_text, "
            "verification_status, verification_date) "
            "VALUES (:sid, :sid, 'https://example.test', 'test', 'CC-BY-4.0', "
            ":tier, :commercial_ok, :sharealike, 'Test Source', 'verified', now())"
        ),
        {
            "sid": source_id,
            "tier": tier,
            "commercial_ok": commercial_ok,
            "sharealike": sharealike,
        },
    )
    return source_id


def insert_ingestion_snapshot(
    session: Session,
    source_id: str,
    snapshot_id: str | None = None,
) -> str:
    """Insert a minimal ingestion_snapshot row and return its id."""
    snapshot_id = snapshot_id or f"snap_{generate_ulid()}"
    session.execute(
        text(
            "INSERT INTO ingestion_snapshot (snapshot_id, source_id, source_version, "
            "acquired_at, content_sha256, byte_size, landing_uri, license_at_time) "
            "VALUES (:sid, :src, 'v1', now(), :sha, 100, 's3://test/', 'CC-BY-4.0')"
        ),
        {"sid": snapshot_id, "src": source_id, "sha": "a" * 64},
    )
    return snapshot_id


def insert_toolchain(session: Session, toolchain_id: str = "test-toolchain") -> str:
    """Insert a minimal toolchain row and return its id."""
    session.execute(
        text(
            "INSERT INTO toolchain (toolchain_id, rdkit_version, python_version, std_pipeline_ver) "
            "VALUES (:tid, '2025.3.3', '3.12.4', 'v1')"
        ),
        {"tid": toolchain_id},
    )
    return toolchain_id


def insert_descriptor_spec(
    session: Session,
    toolchain_id: str,
    descriptor_spec_version: str = "v1",
    feature_set_id: str | None = None,
) -> str:
    """Insert a minimal descriptor_spec row and return its version."""
    feature_set_id = feature_set_id or "b" * 64
    session.execute(
        text(
            "INSERT INTO descriptor_spec (descriptor_spec_version, toolchain_id, "
            "hbd_convention, hba_convention, rotb_strict, descriptor_list, feature_set_id) "
            "VALUES (:v, :tid, 'lipinski', 'lipinski', true, ARRAY['mw_g_mol'], :fsid)"
        ),
        {"v": descriptor_spec_version, "tid": toolchain_id, "fsid": feature_set_id},
    )
    return descriptor_spec_version


def insert_organism(session: Session, taxon_id: int = 9606, name: str = "Homo sapiens") -> int:
    """Insert an organism row (idempotent-ish via ON CONFLICT) and return its taxon_id."""
    session.execute(
        text(
            "INSERT INTO organism (taxon_id, scientific_name) VALUES (:tid, :name) "
            "ON CONFLICT (taxon_id) DO NOTHING"
        ),
        {"tid": taxon_id, "name": name},
    )
    return taxon_id


def insert_compound(
    session: Session,
    *,
    smiles: str = "CCO",
    source_id: str,
    snapshot_id: str,
    toolchain_id: str,
    created_by: str,
    compound_uid: str | None = None,
    inchikey_full: str | None = None,
    is_mixture: bool = False,
    parent_inchikey: str | None = None,
    is_deleted: bool = False,
    deleted_reason: str | None = None,
) -> str:
    """Insert a minimal valid compound row using cartridge SQL functions.

    ``mol_from_smiles`` and ``morganbv_fp`` are RDKit cartridge functions —
    generating the mol/fingerprint values in SQL avoids needing a Python RDKit
    binding in the test environment.

    Returns:
        The compound_uid.
    """
    compound_uid = compound_uid or generate_ulid()
    inchikey_full = inchikey_full or _fake_inchikey(compound_uid)
    session.execute(
        text(
            "INSERT INTO compound (compound_uid, source_smiles, canonical_smiles, "
            "isomeric_smiles, standardized_smiles, inchi, inchikey_full, "
            "inchikey_skeleton, parent_inchikey, molecular_formula, "
            "stereo_completeness, is_mixture, mol, morgan_fp_r2_2048, source_id, "
            "snapshot_id, source_license, license_tier, is_commercial_ok, "
            "toolchain_id, pipeline_version, drugsim_release, created_by, "
            "is_deleted, deleted_reason) "
            "VALUES (:uid, :smiles, :smiles, :smiles, :smiles, 'InChI=1S/test', "
            ":ik, :ikskel, :parent_ik, 'C2H6O', 'not_applicable', :is_mixture, "
            "mol_from_smiles(:smiles), morganbv_fp(mol_from_smiles(:smiles), 2), "
            ":source_id, :snapshot_id, 'CC-BY-4.0', 'amber', true, :toolchain_id, "
            ":pipeline_version, '0.1.0', :created_by, :is_deleted, :deleted_reason)"
        ),
        {
            "uid": compound_uid,
            "smiles": smiles,
            "ik": inchikey_full,
            "ikskel": inchikey_full[:14],
            "parent_ik": parent_inchikey,
            "is_mixture": is_mixture,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "toolchain_id": toolchain_id,
            "pipeline_version": "c" * 40,
            "created_by": created_by,
            "is_deleted": is_deleted,
            "deleted_reason": deleted_reason,
        },
    )
    return compound_uid


def insert_endpoint(
    session: Session,
    endpoint_id: str = "test_endpoint",
    *,
    endpoint_class: str = "toxicity",
    is_categorical: bool = True,
    higher_is_worse: bool | None = True,
    expected_min: float | None = None,
    expected_max: float | None = None,
    unit_verified_method: str = "documented",
) -> str:
    """Insert a minimal endpoint row and return its id."""
    session.execute(
        text(
            "INSERT INTO endpoint (endpoint_id, endpoint_class, display_name, "
            "canonical_unit, is_categorical, higher_is_worse, expected_min, "
            "expected_max, unit_verified_method) "
            "VALUES (:eid, :cls, :eid, 'unitless', :cat, :worse, :emin, :emax, :uvm)"
        ),
        {
            "eid": endpoint_id,
            "cls": endpoint_class,
            "cat": is_categorical,
            "worse": higher_is_worse,
            "emin": expected_min,
            "emax": expected_max,
            "uvm": unit_verified_method,
        },
    )
    return endpoint_id


def insert_target(session: Session, target_uid: str | None = None, source_id: str = "test_source") -> str:
    """Insert a minimal target row and return its id."""
    target_uid = target_uid or generate_ulid()
    session.execute(
        text(
            "INSERT INTO target (target_uid, target_name, target_type, source_id, license_tier) "
            "VALUES (:uid, 'Test Target', 'SINGLE PROTEIN', :sid, 'amber')"
        ),
        {"uid": target_uid, "sid": source_id},
    )
    return target_uid


def insert_protein(
    session: Session,
    protein_uid: str | None = None,
    *,
    uniprot_accession: str = "P00533",
    is_reviewed: bool = True,
    source_id: str = "test_source",
) -> str:
    """Insert a minimal protein row and return its id."""
    protein_uid = protein_uid or generate_ulid()
    session.execute(
        text(
            "INSERT INTO protein (protein_uid, uniprot_accession, is_reviewed, "
            "taxon_id, source_id, license_tier) "
            "VALUES (:uid, :acc, :rev, 9606, :sid, 'amber')"
        ),
        {"uid": protein_uid, "acc": uniprot_accession, "rev": is_reviewed, "sid": source_id},
    )
    return protein_uid


def insert_assay(session: Session, source_id: str, snapshot_id: str) -> str:
    """Insert a minimal assay row and return its id."""
    assay_uid = generate_ulid()
    session.execute(
        text(
            "INSERT INTO assay (assay_uid, source_id, snapshot_id, license_tier) "
            "VALUES (:uid, :sid, :snap, 'amber')"
        ),
        {"uid": assay_uid, "sid": source_id, "snap": snapshot_id},
    )
    return assay_uid


# Crockford base32 — the alphabet the ``ulid`` domain's CHECK constraint accepts.
# Deliberately excludes I, L, O and U to prevent transcription errors, which is
# why a label like "black" or "LT" cannot be dropped into a ULID column verbatim.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def fake_ulid(label: str) -> str:
    """Build a deterministic, syntactically valid ULID from an arbitrary label.

    Tests want readable, stable ids (so a failure names the case that produced
    it), but the ``ulid`` domain only accepts 26 uppercase Crockford base32
    characters. Uppercasing and dropping the excluded letters keeps the id
    recognisable without violating the domain.

    Args:
        label: Any human-readable string, e.g. an evidence type or licence tier.

    Returns:
        A 26-character string that satisfies the ``ulid`` domain constraint.
    """
    cleaned = "".join(c for c in label.upper() if c in _CROCKFORD)
    return cleaned[:26].rjust(26, "0")


def _fake_inchikey(seed: str) -> str:
    """Build a syntactically valid but scientifically meaningless InChIKey from a seed."""
    letters = "".join(c for c in seed.upper() if c.isalpha()) or "A"
    block1 = (letters * 14)[:14]
    block2 = (letters * 10)[:10]
    return f"{block1}-{block2}-{letters[0]}"


def insert_model(
    session: Session,
    endpoint_id: str,
    created_by: str,
    *,
    model_uid: str | None = None,
    methodology: str = "statistical_based",
    model_name: str | None = None,
) -> str:
    """Insert a minimal model row and return its id."""
    model_uid = model_uid or generate_ulid()
    model_name = model_name or f"model_{model_uid}"
    session.execute(
        text(
            "INSERT INTO model (model_uid, model_name, endpoint_id, methodology, "
            "description, created_by) "
            "VALUES (:uid, :name, :eid, :methodology, 'Test model', :created_by)"
        ),
        {"uid": model_uid, "name": model_name, "eid": endpoint_id, "methodology": methodology, "created_by": created_by},
    )
    return model_uid


def insert_model_version(
    session: Session,
    model_uid: str,
    descriptor_spec_version: str,
    training_snapshot_id: str,
    created_by: str,
    *,
    model_version_uid: str | None = None,
    feature_set_id: str | None = None,
    training_license_tiers: list[str] | None = None,
    is_commercial_ok: bool = True,
    is_validated: bool = False,
    is_regulatory_ready: bool = False,
    version: str = "0.1.0",
) -> str:
    """Insert a minimal model_version row and return its id."""
    model_version_uid = model_version_uid or generate_ulid()
    feature_set_id = feature_set_id or "b" * 64
    training_license_tiers = training_license_tiers or ["amber"]
    session.execute(
        text(
            "INSERT INTO model_version (model_version_uid, model_uid, version, "
            "algorithm, hyperparameters, feature_set_id, descriptor_spec_version, "
            "training_snapshot_id, training_license_tiers, is_commercial_ok, "
            "ad_definition, ad_method, artifact_uri, artifact_sha256, is_validated, "
            "is_regulatory_ready, trained_at, created_by) "
            "VALUES (:uid, :model_uid, :version, 'gbm', '{}'::jsonb, :fsid, :dsv, "
            ":snap, :tiers, :commercial_ok, '{}'::jsonb, 'knn_tanimoto', "
            "'s3://test/model', :artifact_sha, :validated, :reg_ready, now(), :created_by)"
        ),
        {
            "uid": model_version_uid,
            "model_uid": model_uid,
            "version": version,
            "fsid": feature_set_id,
            "dsv": descriptor_spec_version,
            "snap": training_snapshot_id,
            "tiers": training_license_tiers,
            "commercial_ok": is_commercial_ok,
            "artifact_sha": "c" * 64,
            "validated": is_validated,
            "reg_ready": is_regulatory_ready,
            "created_by": created_by,
        },
    )
    return model_version_uid


def insert_prediction(
    session: Session,
    compound_uid: str,
    endpoint_id: str,
    model_version_uid: str,
    *,
    prediction_uid: str | None = None,
    feature_set_id: str | None = None,
    predicted_value: float = 1.0,
    ad_verdict: str = "in_domain",
    interval_low: float | None = 0.5,
    interval_high: float | None = 1.5,
) -> str:
    """Insert a minimal prediction row and return its id.

    Note: feature_set_id defaults to the SAME value used by insert_model_version's
    default, so callers who want to test the mismatch trigger must pass a
    DIFFERENT value explicitly.
    """
    prediction_uid = prediction_uid or generate_ulid()
    feature_set_id = feature_set_id or "b" * 64
    session.execute(
        text(
            "INSERT INTO prediction (prediction_uid, compound_uid, endpoint_id, "
            "model_version_uid, predicted_value, predicted_unit, interval_low, "
            "interval_high, confidence_score, ad_verdict, ad_max_tanimoto, "
            "ad_scaffold_seen, feature_set_id, quality_score, quality_formula_version, "
            "is_commercial_ok) "
            "VALUES (:uid, :cuid, :eid, :mvuid, :value, 'unitless', :ilow, :ihigh, "
            "0.8, :ad_verdict, 0.7, false, :fsid, 0.8, 'v1', true)"
        ),
        {
            "uid": prediction_uid,
            "cuid": compound_uid,
            "eid": endpoint_id,
            "mvuid": model_version_uid,
            "value": predicted_value,
            "ilow": interval_low,
            "ihigh": interval_high,
            "ad_verdict": ad_verdict,
            "fsid": feature_set_id,
        },
    )
    return prediction_uid
