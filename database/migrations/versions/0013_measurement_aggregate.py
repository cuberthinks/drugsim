"""Measurement aggregation with discordance flags.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-08

Implements Phase 1 Step 8 §3.3, which was designed in Phase 1 but never built
as DDL until this consolidated Phase 2 pass explicitly requested it: "Do not
silently average conflicting measurements. Use versioned training aggregates
instead."

Self-contained per database/ddl/README.md's policy from migration 0012
onward — this SQL is not read from database/ddl/11_measurement_aggregate.sql
at run time; that file is a hand-kept-in-sync human-readable mirror.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0013"
down_revision: Optional[str] = "0012"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
CREATE TABLE measurement_aggregate (
    aggregate_uid             ulid             PRIMARY KEY,
    compound_uid               ulid            NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    endpoint_id                TEXT            NOT NULL REFERENCES endpoint (endpoint_id) ON DELETE RESTRICT,
    target_uid                 ulid            REFERENCES target (target_uid) ON DELETE RESTRICT,
    aggregated_value           NUMERIC(14, 6)  NOT NULL,
    aggregation_method         TEXT            NOT NULL CHECK (aggregation_method IN (
        'single_value', 'median', 'geometric_mean', 'majority_vote',
        'max_confidence', 'most_recent', 'curator_selected'
    )),
    n_source_measurements      SMALLINT        NOT NULL CHECK (n_source_measurements > 0),
    value_spread_log10         NUMERIC(8, 4),
    is_discordant              BOOLEAN         NOT NULL,
    aggregation_policy_version TEXT            NOT NULL,
    license_tiers_consumed     license_tier_t[] NOT NULL,
    computed_at                TIMESTAMPTZ     NOT NULL DEFAULT now(),
    CONSTRAINT uq_aggregate
        UNIQUE (compound_uid, endpoint_id, target_uid, aggregation_policy_version)
);

CREATE INDEX ix_aggregate_training ON measurement_aggregate (endpoint_id, aggregation_policy_version)
    WHERE NOT is_discordant;

COMMENT ON TABLE measurement_aggregate IS
    'A recorded, versioned DECISION about what value a model trains on, kept '
    'entirely separate from measurement (the immutable individual '
    'observations). A discordant result is retained here, not deleted -- it '
    'is a data-quality finding, not noise: a compound with 100-fold lab '
    'disagreement is not a training example, it is something worth knowing '
    'about (Phase 1 Step 8 §3.3).';

COMMENT ON COLUMN measurement_aggregate.is_discordant IS
    'TRUE excludes this aggregate from training (see ix_aggregate_training). '
    'Set when continuous values span >10x (value_spread_log10 > 1) or a '
    'binary vote ties -- both cases where averaging would manufacture a '
    'confident label for a quantity nobody actually knows.';

COMMENT ON COLUMN measurement_aggregate.aggregation_policy_version IS
    'A policy change (e.g. discordance threshold, potency-vs-other '
    'classification) produces a NEW row set under a new version rather than '
    'overwriting the old one -- so a model trained under policy v1 remains '
    'reproducible after v2 ships.';

CREATE TRIGGER trg_audit_measurement_aggregate
    AFTER INSERT OR UPDATE ON measurement_aggregate
    FOR EACH ROW EXECUTE FUNCTION audit_row_change('aggregate_uid');
"""


def upgrade() -> None:
    """Add measurement_aggregate."""
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
