"""governance domain

Revision ID: 0003
Revises: '0002'
Create Date: 2026-08-06

Generated from database/ddl/02_governance.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0003"
down_revision: Optional[str] = '0002'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Governance domain
-- Phase 1 Step 3 §3, extended by the regulatory addendum (21 CFR Part 11 controls).
--
-- Implementation note: audit_log.audit_uid uses gen_random_uuid(), not the ulid
-- domain used everywhere else. See database/ddl/README.md "Implementation notes"
-- for the reasoning — audit rows are database-generated, not application-generated,
-- and there is no application call site to mint a ULID from.

-- ============================================================================
-- data_source — Z0 registry projection (mirrors datasets/registry.yaml)
-- ============================================================================

CREATE TABLE data_source (
    source_id           TEXT           PRIMARY KEY,
    name                TEXT           NOT NULL,
    homepage            TEXT           NOT NULL,
    role                TEXT           NOT NULL,
    license_spdx        TEXT           NOT NULL,
    license_tier        license_tier_t NOT NULL,
    is_commercial_ok    BOOLEAN        NOT NULL,
    has_sharealike      BOOLEAN        NOT NULL,
    attribution_text    TEXT           NOT NULL,
    cadence_days        INTEGER        CHECK (cadence_days > 0),
    is_split_licensed   BOOLEAN        NOT NULL DEFAULT FALSE,
    verification_status TEXT           NOT NULL
        CHECK (verification_status IN ('verified', 'secondary', 'unverified')),
    verification_date   DATE           NOT NULL,
    notes               TEXT,
    is_active           BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ    NOT NULL DEFAULT now(),
    CONSTRAINT ck_ds_tier_commercial
        CHECK ((license_tier = 'black') = (is_commercial_ok = FALSE)),
    CONSTRAINT ck_ds_tier_sharealike
        CHECK ((license_tier = 'red') = has_sharealike)
);

COMMENT ON TABLE data_source IS
    'Queryable projection of datasets/registry.yaml. The registry file is '
    'authoritative and git-reviewed; this table drives runtime FK integrity and '
    'the license-tier CHECK constraints propagated onto every fact table.';

-- ============================================================================
-- ingestion_snapshot — Z1 landing provenance
-- ============================================================================

CREATE TABLE ingestion_snapshot (
    snapshot_id       TEXT         PRIMARY KEY,
    source_id         TEXT         NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    source_version    TEXT         NOT NULL,
    acquired_at       TIMESTAMPTZ  NOT NULL,
    content_sha256    sha256_hex   NOT NULL,
    byte_size         BIGINT       NOT NULL CHECK (byte_size > 0),
    record_count      BIGINT       CHECK (record_count >= 0),
    landing_uri       TEXT         NOT NULL,
    license_at_time   TEXT         NOT NULL,
    gate_results      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    is_superseded     BOOLEAN      NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_snapshot UNIQUE (source_id, source_version, content_sha256)
);

CREATE INDEX ix_snapshot_source_time ON ingestion_snapshot (source_id, acquired_at DESC);

COMMENT ON COLUMN ingestion_snapshot.license_at_time IS
    'The licence as it stood when we acquired these bytes, independent of '
    'data_source.license_spdx which reflects the current registry entry. A '
    'source that relicenses does not retroactively change the terms under which '
    'we hold an existing snapshot (gate LC-04 diffs these two).';

-- ============================================================================
-- toolchain / descriptor_spec — reproducibility anchors
-- ============================================================================

CREATE TABLE toolchain (
    toolchain_id      TEXT         PRIMARY KEY,
    rdkit_version     TEXT         NOT NULL,
    python_version    TEXT         NOT NULL,
    std_pipeline_ver  TEXT         NOT NULL,
    container_digest  TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE descriptor_spec (
    descriptor_spec_version TEXT       PRIMARY KEY,
    toolchain_id      TEXT             NOT NULL REFERENCES toolchain (toolchain_id) ON DELETE RESTRICT,
    hbd_convention    TEXT             NOT NULL CHECK (hbd_convention IN ('lipinski', 'strict')),
    hba_convention    TEXT             NOT NULL CHECK (hba_convention IN ('lipinski', 'strict')),
    rotb_strict       BOOLEAN          NOT NULL,
    descriptor_list   TEXT[]           NOT NULL,
    feature_set_id    sha256_hex       NOT NULL UNIQUE,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT now()
);

COMMENT ON COLUMN descriptor_spec.hbd_convention IS
    'RDKit''s Lipinski.NumHDonors and rdMolDescriptors.CalcNumHBD disagree for the '
    'same molecule (Phase 1 Step 4 §E.1). Recording the convention in force is '
    'what makes a drug-likeness verdict reproducible rather than unfalsifiable.';

-- ============================================================================
-- system_user — internal operators of the data platform
-- ============================================================================
-- Scope note: this is NOT the customer-facing multi-tenant user model described
-- in TDS §4.7 (which adds tenant_id for customer structure isolation). Sprint 2.2
-- builds the scientific data platform; tenant_id and row-level security are a
-- Phase 7 (Platform Services) concern once customer uploads exist. system_user
-- here identifies curators, scientists and reviewers who operate the pipeline and
-- sign regulatory records — a real requirement now, because audit_log.changed_by
-- and electronic_signature.signer_uid must reference someone.

CREATE TABLE system_user (
    user_uid       ulid        PRIMARY KEY,
    username       TEXT        NOT NULL UNIQUE,
    full_name      TEXT        NOT NULL,
    email          TEXT        NOT NULL,
    role           TEXT        NOT NULL
        CHECK (role IN ('admin', 'curator', 'scientist', 'reviewer', 'service', 'readonly')),
    can_sign       BOOLEAN     NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deactivated_at TIMESTAMPTZ,
    CONSTRAINT ck_user_deactivation CHECK (is_active OR deactivated_at IS NOT NULL)
);

COMMENT ON TABLE system_user IS
    'Users are never hard-deleted (P8): is_active = false with the audit trail '
    'preserved. Under Part 11, an account whose actions are recorded cannot be '
    'removed.';

-- ============================================================================
-- audit_log — append-only, partitioned by month
-- ============================================================================

CREATE TABLE audit_log (
    audit_uid        UUID        NOT NULL DEFAULT gen_random_uuid(),
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    table_name       TEXT        NOT NULL,
    record_pk        TEXT        NOT NULL,
    operation        audit_op_t  NOT NULL,
    old_values       JSONB,
    new_values       JSONB,
    changed_by       ulid        NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    change_reason    TEXT        NOT NULL,
    pipeline_version git_sha,
    PRIMARY KEY (audit_uid, occurred_at),
    CONSTRAINT ck_audit_values CHECK (
        (operation = 'insert' AND old_values IS NULL AND new_values IS NOT NULL)
        OR (operation = 'update' AND old_values IS NOT NULL AND new_values IS NOT NULL)
        OR (operation IN ('soft_delete', 'restore') AND old_values IS NOT NULL)
    ),
    CONSTRAINT ck_audit_reason_not_blank CHECK (btrim(change_reason) <> '')
) PARTITION BY RANGE (occurred_at);

-- A DEFAULT partition guarantees inserts never fail for lack of a partition.
-- Scheduled partition creation ahead of need is an operational task (a cron job
-- or Dagster sensor per TDS §10.9) — see scripts/ensure_audit_partitions.py.
CREATE TABLE audit_log_default PARTITION OF audit_log DEFAULT;

REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC;

COMMENT ON TABLE audit_log IS
    'Append-only. UPDATE and DELETE are revoked at the grant level, not merely by '
    'convention (TDS §7.9). Populated exclusively by the generic audit trigger '
    '(09_triggers.sql), which requires the calling session to set '
    'app.current_user_id and app.change_reason — see src/drugsim_db/audit.py.';

-- ============================================================================
-- electronic_signature — 21 CFR Part 11 §11.50 / §11.70
-- ============================================================================

CREATE TABLE electronic_signature (
    signature_uid     ulid          PRIMARY KEY,
    signed_table      TEXT          NOT NULL,
    signed_record_pk  TEXT          NOT NULL,
    record_hash       sha256_hex    NOT NULL,
    signer_uid        ulid          NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    signature_meaning sig_meaning_t NOT NULL,
    signed_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
    signature_text    TEXT          NOT NULL,
    CONSTRAINT uq_sig UNIQUE (signed_table, signed_record_pk, signer_uid, signature_meaning)
);

CREATE INDEX ix_sig_record ON electronic_signature (signed_table, signed_record_pk);

COMMENT ON COLUMN electronic_signature.record_hash IS
    'Content hash of the signed record at signing time. Implements §11.70 '
    'signature/record linking: a signature is bound to specific content, so '
    'post-signature modification is detectable rather than merely prohibited.';

COMMENT ON CONSTRAINT ck_user_deactivation ON system_user IS
    'A user can only be deactivated (never deleted) — see table comment.';
"""


def upgrade() -> None:
    """Apply 02_governance.sql."""
    op.execute(_SQL)


def downgrade() -> None:
    """Migrations are forward-only (TDS §8.4, §10.6).

    Raises:
        RuntimeError: Always.
    """
    msg = (
        "DrugSim migrations are forward-only. Roll forward with a new migration "
        "rather than downgrading (TDS §8.4)."
    )
    raise RuntimeError(msg)
