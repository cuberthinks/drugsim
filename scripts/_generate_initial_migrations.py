#!/usr/bin/env python3
"""One-time bootstrap: generate Alembic migration files from database/ddl/*.sql.

Run once, at authoring time, for the initial schema only. See
database/ddl/README.md — from the next migration onward, migrations are written
directly (self-contained SQL, no dependency on a file that could change later)
and database/ddl/*.sql becomes a regenerated post-migration snapshot instead.

This script is not part of the ongoing workflow and does not belong in CI.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DDL_DIR = ROOT / "database" / "ddl"
VERSIONS_DIR = ROOT / "database" / "migrations" / "versions"

# (revision, down_revision, ddl_filename, message)
MIGRATIONS = [
    ("0001", None, "00_extensions.sql", "extensions"),
    ("0002", "0001", "01_domains_and_types.sql", "domains and enumerated types"),
    ("0003", "0002", "02_governance.sql", "governance domain"),
    ("0004", "0003", "03_chemistry.sql", "chemistry domain"),
    ("0005", "0004", "04_biology.sql", "biology domain"),
    ("0006", "0005", "05_evidence.sql", "evidence domain: endpoints, assays, measurements"),
    ("0007", "0006", "06_models_and_predictions.sql", "models, validation, and predictions"),
    ("0008", "0007", "07_relations.sql", "relations domain"),
    ("0009", "0008", "08_views.sql", "views"),
    ("0010", "0009", "09_triggers.sql", "triggers: audit capture, feature-set consistency, ICH M7 pairing"),
]

TEMPLATE = '''"""{message}

Revision ID: {revision}
Revises: {down_revision!r}
Create Date: 2026-08-06

Generated from database/ddl/{ddl_filename} at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "{revision}"
down_revision: Optional[str] = {down_revision!r}
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
{sql_body}
"""


def upgrade() -> None:
    """Apply {ddl_filename}."""
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
'''


def main() -> None:
    """Generate one migration file per DDL file."""
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    for revision, down_revision, ddl_filename, message in MIGRATIONS:
        sql_body = (DDL_DIR / ddl_filename).read_text(encoding="utf-8").rstrip("\n")
        content = TEMPLATE.format(
            message=message,
            revision=revision,
            down_revision=down_revision,
            ddl_filename=ddl_filename,
            sql_body=sql_body,
        )
        out_path = VERSIONS_DIR / f"{revision}_{ddl_filename.replace('.sql', '')}.py"
        out_path.write_text(content, encoding="utf-8")
        print(f"wrote {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
