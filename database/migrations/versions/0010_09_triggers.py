"""triggers: audit capture, feature-set consistency, ICH M7 pairing

Revision ID: 0010
Revises: '0009'
Create Date: 2026-08-06

Generated from database/ddl/09_triggers.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0010"
down_revision: Optional[str] = '0009'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Triggers
-- Phase 1 Step 3 §10 named three rules that span tables and cannot be expressed
-- as CHECK constraints. This file implements all three. See database/ddl/README.md
-- for the audit-scope and trigger-timing decisions made while implementing them.

-- ============================================================================
-- 1. Generic audit capture
-- ============================================================================
-- Requires the calling session to set two GUCs before any DML on a governed
-- table:
--
--     SET LOCAL app.current_user_id = '<ulid of a system_user>';
--     SET LOCAL app.change_reason   = '<non-blank reason>';
--
-- Missing either raises and aborts the transaction (TDS §7.9: "if the audit
-- write fails, the transaction fails — an unaudited change is worse than a
-- rejected one"). See src/drugsim_db/audit.py for the Python context manager
-- that sets these correctly, including cleanup.
--
-- Applied to INSERT and UPDATE only. Hard DELETE is revoked at the grant level
-- (02_governance.sql); if a DELETE somehow reaches a governed table despite
-- that, this function raises rather than attempting to log it under an
-- audit_op_t value that does not exist (P8: no hard deletes, not even audited
-- ones — restore the row via UPDATE instead).

CREATE OR REPLACE FUNCTION audit_row_change() RETURNS trigger AS $$
DECLARE
    v_pk_column  TEXT := TG_ARGV[0];
    v_operation  audit_op_t;
    v_old_jsonb  JSONB;
    v_new_jsonb  JSONB;
    v_record_pk  TEXT;
    v_changed_by TEXT;
    v_reason     TEXT;
    v_pipeline   TEXT;
BEGIN
    v_changed_by := current_setting('app.current_user_id', true);
    v_reason     := current_setting('app.change_reason', true);
    v_pipeline   := current_setting('app.pipeline_version', true);

    IF v_changed_by IS NULL OR btrim(v_changed_by) = '' THEN
        RAISE EXCEPTION
            'audit context missing: app.current_user_id must be set before '
            'modifying table %. Use drugsim_db.audit.audit_context(). An '
            'unaudited change is not permitted (TDS §7.9).', TG_TABLE_NAME;
    END IF;
    IF v_reason IS NULL OR btrim(v_reason) = '' THEN
        RAISE EXCEPTION
            'audit context missing: app.change_reason must be set before '
            'modifying table % (TDS §7.9).', TG_TABLE_NAME;
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_operation := 'insert';
        v_new_jsonb := to_jsonb(NEW);
        v_record_pk := v_new_jsonb ->> v_pk_column;

    ELSIF TG_OP = 'UPDATE' THEN
        v_old_jsonb := to_jsonb(OLD);
        v_new_jsonb := to_jsonb(NEW);
        v_record_pk := v_new_jsonb ->> v_pk_column;

        IF v_old_jsonb ? 'is_deleted' THEN
            IF (v_old_jsonb ->> 'is_deleted') = 'false' AND (v_new_jsonb ->> 'is_deleted') = 'true' THEN
                v_operation := 'soft_delete';
            ELSIF (v_old_jsonb ->> 'is_deleted') = 'true' AND (v_new_jsonb ->> 'is_deleted') = 'false' THEN
                v_operation := 'restore';
            ELSE
                v_operation := 'update';
            END IF;
        ELSE
            v_operation := 'update';
        END IF;

    ELSE
        RAISE EXCEPTION
            'audit_row_change does not support operation % on table % — hard '
            'deletes are forbidden (P8); soft-delete via is_deleted instead.',
            TG_OP, TG_TABLE_NAME;
    END IF;

    INSERT INTO audit_log (
        table_name, record_pk, operation, old_values, new_values,
        changed_by, change_reason, pipeline_version
    ) VALUES (
        TG_TABLE_NAME, v_record_pk, v_operation, v_old_jsonb, v_new_jsonb,
        v_changed_by::ulid, v_reason, NULLIF(v_pipeline, '')::git_sha
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION audit_row_change() IS
    'Generic audit trigger. Casts app.current_user_id to the ulid domain and '
    'app.pipeline_version to the git_sha domain, so a malformed identifier fails '
    'loudly at the point of the offending write rather than silently corrupting '
    'the audit trail.';

-- Attached to a named subset of governed, interactively-mutated entities — not
-- every table. Bulk scientific data (measurement, compound_descriptor, ...)
-- carries its own per-row provenance (source_id/snapshot_id/pipeline_version/
-- ingested_at) populated by ETL, which IS its audit trail; see
-- database/ddl/README.md for why that is a deliberate, separate mechanism.

CREATE TRIGGER trg_audit_compound
    AFTER INSERT OR UPDATE ON compound
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('compound_uid');

CREATE TRIGGER trg_audit_system_user
    AFTER INSERT OR UPDATE ON "system_user"
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('user_uid');

CREATE TRIGGER trg_audit_data_source
    AFTER INSERT OR UPDATE ON data_source
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('source_id');

CREATE TRIGGER trg_audit_model
    AFTER INSERT OR UPDATE ON model
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('model_uid');

CREATE TRIGGER trg_audit_model_version
    AFTER INSERT OR UPDATE ON model_version
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('model_version_uid');

CREATE TRIGGER trg_audit_ich_m7_assessment
    AFTER INSERT OR UPDATE ON ich_m7_assessment
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('assessment_uid');

-- ============================================================================
-- 2. Feature-set consistency (rule PR-01)
-- ============================================================================
-- BEFORE, not AFTER: Step 3 §10 named the category without prescribing timing.
-- BEFORE aborts the write before it happens, rather than committing then rolling
-- back — standard practice for a pure validation trigger with no side effects on
-- other rows.

CREATE OR REPLACE FUNCTION check_prediction_feature_set() RETURNS trigger AS $$
DECLARE
    v_model_feature_set sha256_hex;
BEGIN
    SELECT feature_set_id INTO v_model_feature_set
    FROM model_version
    WHERE model_version_uid = NEW.model_version_uid;

    IF v_model_feature_set IS NULL THEN
        RAISE EXCEPTION 'model_version % not found', NEW.model_version_uid;
    END IF;

    IF NEW.feature_set_id IS DISTINCT FROM v_model_feature_set THEN
        RAISE EXCEPTION
            'feature_set_id mismatch: prediction presents %, model_version % '
            'was trained on %. This is the structural prevention of '
            'training/serving skew (TDS §6.6, risk R5) — it must never be '
            'downgraded to a warning.',
            NEW.feature_set_id, NEW.model_version_uid, v_model_feature_set;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_prediction_feature_set_consistency
    BEFORE INSERT OR UPDATE ON prediction
    FOR EACH ROW EXECUTE FUNCTION check_prediction_feature_set();

-- ============================================================================
-- 3. ICH M7 dual-methodology pairing
-- ============================================================================
-- The database-level companion to the two mandatory, distinct FKs on
-- ich_m7_assessment: this verifies the two referenced predictions actually come
-- from models of the required methodology TYPES, which spans three tables
-- (prediction -> model_version -> model) and so cannot be a CHECK constraint.

CREATE OR REPLACE FUNCTION check_ich_m7_methodology_pairing() RETURNS trigger AS $$
DECLARE
    v_rule_based_methodology  methodology_t;
    v_statistical_methodology methodology_t;
BEGIN
    SELECT m.methodology INTO v_rule_based_methodology
    FROM prediction p
    JOIN model_version mv ON mv.model_version_uid = p.model_version_uid
    JOIN model m ON m.model_uid = mv.model_uid
    WHERE p.prediction_uid = NEW.rule_based_prediction_uid;

    SELECT m.methodology INTO v_statistical_methodology
    FROM prediction p
    JOIN model_version mv ON mv.model_version_uid = p.model_version_uid
    JOIN model m ON m.model_uid = mv.model_uid
    WHERE p.prediction_uid = NEW.statistical_prediction_uid;

    IF v_rule_based_methodology IS DISTINCT FROM 'expert_rule_based' THEN
        RAISE EXCEPTION
            'ICH M7 requires rule_based_prediction_uid to come from an '
            'expert_rule_based model; prediction % comes from a % model. '
            'ICH M7(R2) mandates two COMPLEMENTARY methodologies.',
            NEW.rule_based_prediction_uid, v_rule_based_methodology;
    END IF;

    IF v_statistical_methodology IS DISTINCT FROM 'statistical_based' THEN
        RAISE EXCEPTION
            'ICH M7 requires statistical_prediction_uid to come from a '
            'statistical_based model; prediction % comes from a % model.',
            NEW.statistical_prediction_uid, v_statistical_methodology;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ich_m7_methodology_pairing
    BEFORE INSERT OR UPDATE ON ich_m7_assessment
    FOR EACH ROW EXECUTE FUNCTION check_ich_m7_methodology_pairing();

COMMENT ON FUNCTION check_ich_m7_methodology_pairing() IS
    'Verified against FDA M7(R2) guidance: absence of alerts from two '
    'complementary (Q)SAR methodologies — one expert rule-based, one '
    'statistical — is what permits a "no mutagenic concern" conclusion. This '
    'trigger makes pairing them incorrectly a hard database error rather than a '
    'code-review-dependent convention.';
"""


def upgrade() -> None:
    """Apply 09_triggers.sql."""
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
