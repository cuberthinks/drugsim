"""relations domain

Revision ID: 0008
Revises: '0007'
Create Date: 2026-08-06

Generated from database/ddl/07_relations.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0008"
down_revision: Optional[str] = '0007'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Relations domain (knowledge-graph shaped, modelled relationally)
-- Phase 1 Step 3 §8. Materialised into Neo4j in Phase 6 if a named module
-- justifies it (ADR-004); modelled here as ordinary relational tables in the
-- meantime, which recursive CTEs traverse adequately to 2-3 hops.

CREATE TABLE drug_target_interaction (
    dti_uid        ulid           PRIMARY KEY,
    compound_uid   ulid           NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    target_uid     ulid           NOT NULL REFERENCES target (target_uid) ON DELETE RESTRICT,
    action_type    TEXT           CHECK (action_type IN (
        'INHIBITOR', 'ANTAGONIST', 'AGONIST', 'BLOCKER', 'MODULATOR', 'OPENER', 'ACTIVATOR',
        'POSITIVE ALLOSTERIC MODULATOR', 'NEGATIVE ALLOSTERIC MODULATOR',
        'PARTIAL AGONIST', 'INVERSE AGONIST', 'SUBSTRATE', 'RELEASING AGENT', 'SEQUESTERING AGENT'
    )),
    is_direct        BOOLEAN,
    disease_efficacy BOOLEAN,
    mechanism_text   TEXT,
    evidence_type    evidence_type_t NOT NULL,
    source_id        TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    license_tier     license_tier_t NOT NULL,
    CONSTRAINT uq_dti UNIQUE (compound_uid, target_uid, action_type, source_id)
);

CREATE INDEX ix_dti_target ON drug_target_interaction (target_uid);

CREATE TABLE protein_pathway (
    protein_uid ulid NOT NULL REFERENCES protein (protein_uid) ON DELETE RESTRICT,
    pathway_uid ulid NOT NULL REFERENCES pathway (pathway_uid) ON DELETE RESTRICT,
    source_id   TEXT NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    PRIMARY KEY (protein_uid, pathway_uid, source_id)
);

CREATE TABLE target_disease_association (
    target_uid         ulid           NOT NULL REFERENCES target (target_uid) ON DELETE RESTRICT,
    disease_uid        ulid           NOT NULL REFERENCES disease (disease_uid) ON DELETE RESTRICT,
    association_score  NUMERIC(6, 5)  CHECK (association_score BETWEEN 0 AND 1),
    evidence_count     INTEGER        CHECK (evidence_count >= 0),
    source_id          TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    license_tier       license_tier_t NOT NULL,
    PRIMARY KEY (target_uid, disease_uid, source_id)
);

CREATE TABLE compound_adverse_event (
    cae_uid        ulid           PRIMARY KEY,
    compound_uid   ulid           NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    meddra_pt_code TEXT           NOT NULL,
    meddra_version TEXT           NOT NULL,
    report_count   INTEGER        CHECK (report_count >= 0),
    prr            NUMERIC(10, 4) CHECK (prr >= 0),
    ror            NUMERIC(10, 4) CHECK (ror >= 0),
    ror_ci_low     NUMERIC(10, 4),
    ror_ci_high    NUMERIC(10, 4),
    is_signal      BOOLEAN,
    source_id      TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    license_tier   license_tier_t NOT NULL,
    CONSTRAINT uq_cae UNIQUE (compound_uid, meddra_pt_code, meddra_version, source_id)
);

COMMENT ON TABLE compound_adverse_event IS
    'Stores disproportionality statistics (PRR, ROR + confidence bounds), not raw '
    'counts alone. Naive FAERS counting produces confidently wrong safety signals '
    '(Phase 1 Step 1 §4.1); is_signal is a computed verdict, not an eyeballed one. '
    'meddra_version is mandatory because MedDRA terms change between versions — '
    'the reason SIDER''s MedDRA 16.1 data cannot be merged naively with current '
    'coding.';
"""


def upgrade() -> None:
    """Apply 07_relations.sql."""
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
