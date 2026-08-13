"""extensions

Revision ID: 0001
Revises: None
Create Date: 2026-08-06

Generated from database/ddl/00_extensions.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0001"
down_revision: Optional[str] = None
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Extensions
-- Phase 1 ADR-003: the RDKit cartridge is the reason Postgres is self-managed
-- (unavailable on RDS/Cloud SQL/Aurora). It is what makes substructure (@>) and
-- Tanimoto (%) search possible in SQL with GiST indexes, over ~3M compounds,
-- instead of an application-layer scan.

CREATE EXTENSION IF NOT EXISTS rdkit;

-- Required for gen_random_uuid(), used by audit_log.audit_uid.
-- See database/ddl/README.md "Implementation notes" for why audit rows use UUID
-- rather than the application-generated ulid domain.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'rdkit') THEN
        RAISE EXCEPTION
            'RDKit cartridge failed to install. DrugSim cannot function without it '
            '(ADR-003) — check that the postgres-rdkit image is in use, not stock '
            'postgres:16.';
    END IF;
END $$;
"""


def upgrade() -> None:
    """Apply 00_extensions.sql."""
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
