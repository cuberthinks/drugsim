"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = ${repr(up_revision)}
down_revision: Optional[str] = ${repr(down_revision)}
branch_labels: Optional[str] = ${repr(branch_labels)}
depends_on: Optional[str] = ${repr(depends_on)}


def upgrade() -> None:
    """Apply this migration."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Migrations are forward-only (TDS §8.4, §10.6).

    Raises:
        RuntimeError: Always. Roll forward with a new migration instead of back
            with this one — a silent schema reversal leaves no audit trace, which
            is unacceptable under the regulatory path.
    """
    msg = (
        "DrugSim migrations are forward-only. Roll forward with a new migration "
        "rather than downgrading (TDS §8.4)."
    )
    raise RuntimeError(msg)
