"""Enforce audit-log immutability and one-scaffold-one-split-group for real.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-24

Two controls in the original schema were written as enforcement but behaved as
convention. The constraint test suite (``tests/constraints/``) surfaced both the
first time it was actually executed against a live PostgreSQL.

**audit_log immutability.** ``REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC``
(migration 0003) does not bind the table owner: an owner always retains full
privileges on its own tables regardless of what is revoked from PUBLIC, and no
separate least-privilege role exists anywhere in ``database/``. Whichever
account runs the migrations therefore owns every table and could freely
``DELETE FROM audit_log`` -- the exact thing TDS §7.9 says must be impossible.
A trigger binds the owner where a grant does not, so immutability is now
enforced by one. The REVOKE is deliberately kept: the two are complementary,
and dropping it would weaken the non-owner path.

**uq_scaffold_single_group.** The index was declared
``UNIQUE (scaffold_key, split_group)`` (migration 0004), which cannot express
the property its own comment claims. That composite index makes the *pair*
unique, so it rejects two compounds legitimately sharing a scaffold within one
split group, while happily accepting the same scaffold in two different groups
-- precisely backwards, and precisely the leakage it was written to prevent.
The property needed is functional: ``scaffold_key`` determines ``split_group``.
That cannot be a plain unique index on this table, so it becomes a small
keyed side table plus a trigger that upserts into it. ``ON CONFLICT DO NOTHING``
takes a row lock, so concurrent inserts of the same scaffold serialise rather
than racing.

Self-contained per database/ddl/README.md's policy from migration 0012 onward.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0014"
down_revision: Optional[str] = "0013"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- ============================================================================
-- 1. audit_log immutability, enforced against the table owner
-- ============================================================================

CREATE OR REPLACE FUNCTION reject_audit_log_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log is append-only: % on audit_log is not permitted (TDS §7.9)',
        TG_OP
        USING ERRCODE = 'insufficient_privilege',
              HINT = 'Correct a wrong entry by appending a compensating record, never by editing history.';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION reject_audit_log_mutation() IS
    'Blocks UPDATE/DELETE on audit_log. Exists because REVOKE ... FROM PUBLIC '
    'does not bind the table owner, so the grant alone left history editable '
    'by the account that runs migrations.';

-- A row-level BEFORE trigger on a partitioned table is cloned onto every
-- partition, including partitions created later by
-- scripts/ensure_audit_partitions.py -- so this also covers someone targeting
-- a monthly partition directly rather than going through the parent.
CREATE TRIGGER trg_audit_log_immutable
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION reject_audit_log_mutation();

-- The row trigger only fires for rows that actually match. A statement that
-- matches nothing (e.g. UPDATE on an empty audit_log) would otherwise succeed
-- silently and report "0 rows" rather than being refused, which makes the
-- guarantee depend on whether history happens to be empty. This makes the
-- refusal unconditional through the parent table.
CREATE TRIGGER trg_audit_log_immutable_stmt
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_log_mutation();

COMMENT ON TABLE audit_log IS
    'Append-only, enforced by the trg_audit_log_immutable trigger (which binds '
    'the table owner) as well as by REVOKE UPDATE, DELETE FROM PUBLIC (which '
    'does not). TDS §7.9. Populated exclusively by the generic audit trigger '
    '(09_triggers.sql), which requires the calling session to set '
    'app.current_user_id and app.change_reason -- see src/drugsim_db/audit.py. '
    'Residual risk, disclosed: a superuser can still bypass this via '
    'session_replication_role, and the table owner can ALTER TABLE ... DISABLE '
    'TRIGGER. Closing that requires running the application as a role that owns '
    'nothing, which is a deployment change, not a schema change.';

-- ============================================================================
-- 2. One scaffold, one split group -- the property the old index claimed
-- ============================================================================

-- The authoritative scaffold -> split_group map. scaffold_key is the PRIMARY
-- KEY, so a scaffold physically cannot hold two groups.
CREATE TABLE scaffold_split_group (
    scaffold_key TEXT    PRIMARY KEY,
    split_group  INTEGER NOT NULL CHECK (split_group BETWEEN 0 AND 9)
);

COMMENT ON TABLE scaffold_split_group IS
    'Authoritative scaffold -> split_group assignment. Separate from '
    'compound_split_assignment because the guarantee is functional (one '
    'scaffold determines one group), which a unique index on the compound '
    'table cannot express -- see this migration''s docstring.';

-- Adopt whatever assignment already exists. DISTINCT collapses the normal case
-- of many compounds sharing one scaffold in one group; a scaffold genuinely
-- split across two groups would violate the PRIMARY KEY and abort the
-- migration, which is the correct outcome -- that is pre-existing leakage and
-- must be resolved deliberately, not silently collapsed to one group.
INSERT INTO scaffold_split_group (scaffold_key, split_group)
SELECT DISTINCT scaffold_key, split_group FROM compound_split_assignment;

-- The old index expressed the wrong property in both directions: it rejected
-- two compounds sharing a scaffold within one group (legitimate) and allowed
-- one scaffold across two groups (the leakage).
DROP INDEX IF EXISTS uq_scaffold_single_group;

CREATE OR REPLACE FUNCTION enforce_scaffold_single_group() RETURNS TRIGGER AS $$
DECLARE
    existing_group INTEGER;
BEGIN
    -- Claim the scaffold for this group if unclaimed. ON CONFLICT takes a row
    -- lock, so two concurrent transactions inserting the same scaffold
    -- serialise here instead of both reading "unclaimed" and diverging.
    INSERT INTO scaffold_split_group (scaffold_key, split_group)
    VALUES (NEW.scaffold_key, NEW.split_group)
    ON CONFLICT (scaffold_key) DO NOTHING;

    SELECT split_group INTO existing_group
    FROM scaffold_split_group
    WHERE scaffold_key = NEW.scaffold_key;

    IF existing_group IS DISTINCT FROM NEW.split_group THEN
        RAISE EXCEPTION
            'scaffold leakage: scaffold_key % is already assigned to split_group %, '
            'cannot also assign it to split_group % (ADR-009)',
            NEW.scaffold_key, existing_group, NEW.split_group
            USING ERRCODE = 'integrity_constraint_violation',
                  HINT = 'A scaffold must live in exactly one split group, or train and test overlap.';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION enforce_scaffold_single_group() IS
    'Enforces one-scaffold-one-split-group, replacing uq_scaffold_single_group, '
    'which asserted uniqueness of the (scaffold_key, split_group) pair -- a '
    'different and backwards property.';

CREATE TRIGGER trg_scaffold_single_group
    BEFORE INSERT OR UPDATE OF scaffold_key, split_group ON compound_split_assignment
    FOR EACH ROW EXECUTE FUNCTION enforce_scaffold_single_group();

-- ============================================================================
-- 3. Let a non-black source still be flagged not-commercially-clean
-- ============================================================================

-- ck_ds_tier_commercial was a biconditional:
--     (license_tier = 'black') = (is_commercial_ok = FALSE)
-- which asserts that tier ALONE determines commercial usability. That holds for
-- a uniformly licensed source but not for a split-licensed one: TDC resolves to
-- an amber effective tier (its default is CC-BY-4.0) while being only
-- conditionally usable commercially, because it carries a hard-gated
-- CC-BY-NC-SA FreeSolv exclusion. Under the biconditional that row is
-- unrepresentable, so syncing the project's own registry failed outright.
--
-- The direction that actually matters is preserved as an implication: a black
-- source can never be commercially OK. The converse is dropped, so a non-black
-- source may still be marked not-commercially-clean.
ALTER TABLE data_source DROP CONSTRAINT ck_ds_tier_commercial;

ALTER TABLE data_source ADD CONSTRAINT ck_ds_tier_commercial
    CHECK (license_tier <> 'black' OR is_commercial_ok = FALSE);

COMMENT ON CONSTRAINT ck_ds_tier_commercial ON data_source IS
    'Black tier implies not commercially usable. Deliberately an implication, '
    'not a biconditional: a split-licensed source (is_split_licensed) can sit '
    'at a non-black effective tier and still be only conditionally usable.';
"""


def upgrade() -> None:
    """Apply the audit-log and scaffold-leakage enforcement fixes."""
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
