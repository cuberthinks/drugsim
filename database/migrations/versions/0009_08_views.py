"""views

Revision ID: 0009
Revises: '0008'
Create Date: 2026-08-06

Generated from database/ddl/08_views.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0009"
down_revision: Optional[str] = '0008'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Views
-- Phase 1 Step 4 §8. ADMET domain views (admet_absorption, etc., Phase 1 Step 5
-- §1) are deferred until endpoint rows exist for those classes — a view over an
-- empty table adds nothing to verify.

-- ============================================================================
-- compound_property_resolved — experimental-over-predicted resolution
-- ============================================================================
-- Created by the Step 4 §1 correction: once logD/logS moved out of
-- compound_descriptor into measurement/prediction, a chemist asking "what is
-- this compound's logD?" needs a resolution rule across both sources.
--
-- Precedence: experimental beats predicted; among experimental, higher
-- confidence and more recent; among predicted, in-domain beats out-of-domain,
-- then higher quality score.
--
-- The `provenance` column is mandatory in any consumer of this view — it is a
-- convenience that makes it easy to forget whether a number was measured or
-- guessed, which is precisely the confusion P4 exists to prevent.

CREATE VIEW compound_property_resolved AS
WITH exp AS (
    SELECT
        m.compound_uid,
        m.endpoint_id,
        m.canonical_value,
        m.canonical_unit,
        'experimental'::TEXT AS provenance,
        m.confidence_score   AS score,
        m.ingested_at        AS as_of,
        NULL::ad_verdict_t   AS ad_verdict,
        m.license_tier,
        1                    AS precedence
    FROM measurement m
    WHERE m.measurement_status = 'measured'
      AND m.value_relation = '='
      AND NOT m.is_deleted
), pred AS (
    SELECT
        p.compound_uid,
        p.endpoint_id,
        p.predicted_value    AS canonical_value,
        p.predicted_unit     AS canonical_unit,
        'predicted'::TEXT    AS provenance,
        p.quality_score      AS score,
        p.predicted_at       AS as_of,
        p.ad_verdict,
        NULL::license_tier_t AS license_tier,
        2                    AS precedence
    FROM prediction p
)
SELECT DISTINCT ON (compound_uid, endpoint_id) *
FROM (SELECT * FROM exp UNION ALL SELECT * FROM pred) u
ORDER BY
    compound_uid, endpoint_id, precedence,
    (ad_verdict IS DISTINCT FROM 'out_of_domain') DESC,
    score DESC NULLS LAST,
    as_of DESC;

COMMENT ON VIEW compound_property_resolved IS
    'Consumers MUST surface the provenance column and, where predicted, '
    'ad_verdict. This is a review checkpoint for any UI or report built on this '
    'view, not merely a recommendation (Phase 1 Step 4 §8).';
"""


def upgrade() -> None:
    """Apply 08_views.sql."""
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
