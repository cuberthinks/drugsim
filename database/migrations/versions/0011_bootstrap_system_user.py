"""Bootstrap the system service account.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-06

This is hand-written, not generated from database/ddl/ — it is seed data (DML),
not schema (DDL), and is fundamentally different in kind from migrations
0001-0010.

Why this migration exists: every governed-table write requires
app.current_user_id to be set to a valid system_user.user_uid, enforced by the
audit trigger (09_triggers.sql). That creates a genuine chicken-and-egg problem
for the very first system_user row — there is no existing user for it to be
attributed to. This migration resolves it once, explicitly: it disables the
audit trigger for the single INSERT that creates the bootstrap account, then
re-enables it immediately. This is a deliberate, narrowly-scoped, documented
exception for a genesis event, not a precedent for skipping audit elsewhere.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0011"
down_revision: Optional[str] = "0010"
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

# Must match drugsim_core.ids.SYSTEM_USER_UID exactly. Duplicated as a literal
# (rather than imported) because migrations must remain runnable independent of
# the application package's evolution — see database/ddl/README.md on why
# migrations are self-contained.
SYSTEM_USER_UID = "0000000000SYSTEM0000000000"


def upgrade() -> None:
    """Create the bootstrap 'system' service account."""
    op.execute(
        f"""
        ALTER TABLE "system_user" DISABLE TRIGGER trg_audit_system_user;

        INSERT INTO "system_user" (user_uid, username, full_name, email, role, can_sign, is_active)
        VALUES (
            '{SYSTEM_USER_UID}',
            'system',
            'DrugSim System Service Account',
            'system@drugsim.internal',
            'service',
            FALSE,
            TRUE
        );

        ALTER TABLE "system_user" ENABLE TRIGGER trg_audit_system_user;
        """
    )


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
