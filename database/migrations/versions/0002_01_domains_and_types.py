"""domains and enumerated types

Revision ID: 0002
Revises: '0001'
Create Date: 2026-08-06

Generated from database/ddl/01_domains_and_types.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0002"
down_revision: Optional[str] = '0001'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Shared domains and enumerated types
-- Phase 1 Step 3 §2. A rule declared once as a domain cannot drift the way a
-- CHECK repeated across forty tables inevitably would — this matters more in a
-- validated system, where a constraint change is itself a controlled event.

-- ============================================================================
-- Domains
-- ============================================================================

-- Application-generated surrogate key. Matches drugsim_core.ids.ULID_RE exactly:
-- Crockford base32 (excludes I, L, O, U to prevent transcription errors),
-- 26 characters, first 10 encoding a millisecond timestamp.
CREATE DOMAIN ulid AS CHAR(26)
    CHECK (VALUE ~ '^[0-9A-HJKMNP-TV-Z]{26}$');

CREATE DOMAIN inchikey27 AS CHAR(27)
    CHECK (VALUE ~ '^[A-Z]{14}-[A-Z]{10}-[A-Z]$');

CREATE DOMAIN inchikey14 AS CHAR(14)
    CHECK (VALUE ~ '^[A-Z]{14}$');

CREATE DOMAIN uniprot_acc AS VARCHAR(10)
    CHECK (VALUE ~ '^[OPQ][0-9][A-Z0-9]{3}[0-9]([A-Z0-9]{4}[0-9])?$'
        OR VALUE ~ '^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$');

CREATE DOMAIN prob_unit AS NUMERIC(6, 5)
    CHECK (VALUE BETWEEN 0 AND 1);

CREATE DOMAIN sha256_hex AS CHAR(64)
    CHECK (VALUE ~ '^[a-f0-9]{64}$');

CREATE DOMAIN git_sha AS CHAR(40)
    CHECK (VALUE ~ '^[a-f0-9]{40}$');

CREATE DOMAIN semver AS TEXT
    CHECK (VALUE ~ '^\d+\.\d+\.\d+$');

-- ============================================================================
-- Enumerated types
-- ============================================================================

CREATE TYPE license_tier_t AS ENUM ('green', 'amber', 'red', 'black');

CREATE TYPE meas_status_t AS ENUM (
    'measured', 'not_measured', 'below_loq', 'above_loq',
    'inconclusive', 'withdrawn_by_source'
);

CREATE TYPE value_relation_t AS ENUM ('=', '<', '<=', '>', '>=', '~');

CREATE TYPE evidence_type_t AS ENUM (
    'experimental', 'predicted', 'derived',
    'expert_curated', 'text_mined', 'inferred_by_homology'
);

CREATE TYPE ad_verdict_t AS ENUM (
    'in_domain', 'borderline', 'out_of_domain', 'undeterminable'
);

CREATE TYPE stereo_state_t AS ENUM (
    'fully_defined', 'partially_defined', 'undefined', 'not_applicable'
);

CREATE TYPE endpoint_class_t AS ENUM (
    'absorption', 'distribution', 'metabolism', 'excretion',
    'toxicity', 'physicochemical', 'bioactivity'
);

CREATE TYPE audit_op_t AS ENUM ('insert', 'update', 'soft_delete', 'restore');

CREATE TYPE sig_meaning_t AS ENUM (
    'authorship', 'review', 'approval', 'responsibility', 'verification'
);

CREATE TYPE methodology_t AS ENUM (
    'expert_rule_based', 'statistical_based', 'hybrid', 'read_across'
);

CREATE TYPE ich_m7_class_t AS ENUM (
    'class_1', 'class_2', 'class_3', 'class_4', 'class_5'
);

CREATE TYPE oecd_principle_t AS ENUM (
    'defined_endpoint', 'unambiguous_algorithm', 'applicability_domain',
    'performance_measures', 'mechanistic_interpretation'
);

CREATE TYPE review_outcome_t AS ENUM (
    'confirms_prediction', 'overrides_prediction', 'inconclusive_further_testing_required'
);
"""


def upgrade() -> None:
    """Apply 01_domains_and_types.sql."""
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
