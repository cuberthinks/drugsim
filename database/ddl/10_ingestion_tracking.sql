-- DrugSim — Ingestion run tracking
-- Sprint 2.3. Fills a gap between what Phase 1 Step 3 specified and what the
-- sprint brief asks for explicitly: parser version, import version, and
-- validation status as first-class, queryable fields.
--
-- Phase 1's ingestion_snapshot (02_governance.sql) records the raw bytes landed
-- at Z1 — source, version, checksum, download date. It carries a `gate_results
-- JSONB` column intended to capture pipeline outcomes, but left unstructured.
-- This table makes that structured: an ingestion_run is one attempt to process
-- a snapshot through a specific parser and importer, with an explicit outcome.
-- The distinction matters because a single snapshot can be reprocessed — a
-- parser bug fix should produce a new run against the SAME immutable snapshot,
-- not a new snapshot (Z1 is write-once; reprocessing is not re-downloading).

CREATE TYPE validation_status_t AS ENUM (
    'pending', 'passed', 'passed_with_warnings', 'failed'
);

CREATE TABLE ingestion_run (
    run_uid              ulid                PRIMARY KEY,
    snapshot_id          TEXT                NOT NULL REFERENCES ingestion_snapshot (snapshot_id) ON DELETE RESTRICT,
    parser_version        git_sha            NOT NULL,
    import_version        git_sha            NOT NULL,
    validation_status     validation_status_t NOT NULL DEFAULT 'pending',
    gate_results          JSONB              NOT NULL DEFAULT '{}'::jsonb,
    records_parsed        BIGINT             CHECK (records_parsed >= 0),
    records_imported      BIGINT             CHECK (records_imported >= 0),
    records_quarantined   BIGINT             CHECK (records_quarantined >= 0),
    started_at            TIMESTAMPTZ        NOT NULL DEFAULT now(),
    completed_at          TIMESTAMPTZ,
    error_summary         TEXT,
    started_by            ulid               NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    CONSTRAINT ck_completed_after_started
        CHECK (completed_at IS NULL OR completed_at >= started_at),
    CONSTRAINT ck_terminal_status_requires_completion
        CHECK (validation_status = 'pending' OR completed_at IS NOT NULL),
    CONSTRAINT ck_imported_le_parsed
        CHECK (records_imported IS NULL OR records_parsed IS NULL OR records_imported <= records_parsed)
);

CREATE INDEX ix_ingestion_run_snapshot ON ingestion_run (snapshot_id, started_at DESC);
CREATE INDEX ix_ingestion_run_status   ON ingestion_run (validation_status) WHERE validation_status <> 'passed';

COMMENT ON TABLE ingestion_run IS
    'One row per attempt to process a snapshot. Multiple runs can reference the '
    'same snapshot_id — a parser fix reprocesses the same immutable Z1 bytes, it '
    'does not re-download them. gate_results mirrors the structure of Phase 1 '
    'Step 2 gates G1-G6 for this run, keyed by gate id.';

COMMENT ON CONSTRAINT ck_terminal_status_requires_completion ON ingestion_run IS
    'A run cannot be marked passed/failed/passed_with_warnings without a '
    'completed_at timestamp — prevents a partially-run pipeline from reporting a '
    'false terminal status.';

CREATE TRIGGER trg_audit_ingestion_run
    AFTER INSERT OR UPDATE ON ingestion_run
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('run_uid');
