"""Audit context management.

The generic audit trigger (``database/ddl/09_triggers.sql``) requires two
session-local settings before any write to a governed table:
``app.current_user_id`` and ``app.change_reason``. This module is the one place
that sets them, so the pattern is applied consistently rather than reimplemented
(with varying degrees of correctness) at every call site.

Security note: ``change_reason`` is free text supplied by a human. Building the
``SET LOCAL`` statement by string-formatting that text into SQL would be a SQL
injection vector — exactly the kind of input-handling mistake TDS §7.7 warns
against, just in a different part of the system. This module uses
``set_config(name, value, is_local)`` with bound parameters instead, which is the
parameterisable equivalent of ``SET LOCAL`` and carries no such risk.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_core.errors import ConfigurationError
from drugsim_core.ids import ULID_RE

__all__ = ["audit_context"]


@contextmanager
def audit_context(
    session: Session,
    *,
    user_id: str,
    reason: str,
    pipeline_version: str | None = None,
) -> Iterator[None]:
    """Set the audit trail attribution for writes made within this block.

    ``set_config(..., is_local=true)`` scopes the setting to the current
    transaction, matching ``SET LOCAL`` semantics: it is automatically cleared
    at commit or rollback, so there is nothing to clean up and no risk of a
    setting leaking into an unrelated later transaction on a pooled connection.

    Args:
        session: An active session. Must be used within an explicit transaction
            for the ``is_local`` scoping to take effect as intended — a bare
            autocommit statement would otherwise behave like a session-wide
            ``SET``, which is the leak this function exists to avoid.
        user_id: A ``system_user.user_uid``. Validated locally against the ULID
            format so a malformed value fails before reaching the database,
            with a message a caller can act on — the domain CHECK on the
            database side would otherwise raise a much less specific error deep
            inside the first triggered write.
        reason: Non-blank justification for the change. Required by the audit
            trigger; an audit entry without a reason is close to worthless
            (TDS §7.9).
        pipeline_version: Git SHA of the code performing the write, if
            applicable. Omit for interactive/manual changes.

    Yields:
        Nothing. Perform the governed writes inside the ``with`` block.

    Raises:
        ConfigurationError: If ``user_id`` is not a well-formed ULID or
            ``reason`` is blank. Checked here rather than left for the database
            trigger, so the error is specific and immediate.

    Example:
        >>> with session_scope() as session:
        ...     with audit_context(session, user_id=curator_uid, reason="manual QA correction"):
        ...         session.execute(update_stmt)
    """
    if not ULID_RE.match(user_id):
        msg = f"user_id must be a valid ULID, got {user_id!r}"
        raise ConfigurationError(msg, user_id=user_id)
    if not reason.strip():
        msg = "reason must not be blank — required by the audit trigger (TDS §7.9)"
        raise ConfigurationError(msg)

    session.execute(text("SELECT set_config('app.current_user_id', :v, true)"), {"v": user_id})
    session.execute(text("SELECT set_config('app.change_reason', :v, true)"), {"v": reason})
    if pipeline_version is not None:
        session.execute(
            text("SELECT set_config('app.pipeline_version', :v, true)"),
            {"v": pipeline_version},
        )
    yield
