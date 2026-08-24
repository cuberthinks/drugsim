"""Constraint and trigger tests: the generic audit trigger.

Proves TDS §7.9's rule — "if the audit write fails, the transaction fails" — is
real: a governed-table write without the required session context raises rather
than silently proceeding unaudited.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from drugsim_core.ids import SYSTEM_USER_UID, generate_ulid
from drugsim_db.audit import audit_context

from .factories import insert_data_source

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


class TestAuditContextIsMandatory:
    """A write to a governed table without app.current_user_id / app.change_reason
    must fail, not proceed unaudited."""

    def test_insert_without_any_context_raises(self, session: Session) -> None:
        with pytest.raises(DBAPIError, match="audit context missing"):
            insert_data_source(session, "no_context_source")
            session.flush()

    def test_insert_with_only_user_id_raises(self, session: Session) -> None:
        session.execute(
            text("SELECT set_config('app.current_user_id', :v, true)"),
            {"v": SYSTEM_USER_UID},
        )
        with pytest.raises(DBAPIError, match="change_reason"):
            insert_data_source(session, "half_context_source")
            session.flush()

    def test_insert_with_only_reason_raises(self, session: Session) -> None:
        session.execute(
            text("SELECT set_config('app.change_reason', :v, true)"), {"v": "test"}
        )
        with pytest.raises(DBAPIError, match="current_user_id"):
            insert_data_source(session, "half_context_source2")
            session.flush()

    def test_full_context_succeeds(self, session: Session) -> None:
        with audit_context(session, user_id=SYSTEM_USER_UID, reason="test insert"):
            insert_data_source(session, "with_context_source")
        session.flush()  # must not raise

    def test_malformed_user_id_in_guc_raises_on_domain_cast(self, session: Session) -> None:
        """Even if a caller bypasses audit_context and sets the GUC directly, the
        trigger's own cast to the ulid domain rejects a malformed value."""
        session.execute(
            text("SELECT set_config('app.current_user_id', 'not-a-ulid', true)")
        )
        session.execute(text("SELECT set_config('app.change_reason', 'x', true)"))
        with pytest.raises(DBAPIError):
            insert_data_source(session, "bad_user_guc_source")
            session.flush()


class TestAuditLogCapturesChanges:
    """Content correctness of the audit trail, not just that it exists."""

    def test_insert_is_captured_with_correct_operation(
        self, session: Session, curator_user_id: str
    ) -> None:
        with audit_context(session, user_id=curator_user_id, reason="creating a source"):
            insert_data_source(session, "captured_source")
        session.flush()

        row = session.execute(
            text(
                "SELECT operation, changed_by, change_reason, old_values, new_values "
                "FROM audit_log WHERE table_name = 'data_source' AND record_pk = 'captured_source'"
            )
        ).one()
        assert row.operation == "insert"
        assert row.changed_by == curator_user_id
        assert row.change_reason == "creating a source"
        assert row.old_values is None
        assert row.new_values is not None

    def test_update_is_captured_with_both_old_and_new(
        self, session: Session, curator_user_id: str
    ) -> None:
        with audit_context(session, user_id=curator_user_id, reason="initial creation"):
            insert_data_source(session, "updateable_source", tier="amber", commercial_ok=True)
        session.flush()

        with audit_context(session, user_id=curator_user_id, reason="marking inactive"):
            session.execute(
                text("UPDATE data_source SET is_active = false WHERE source_id = 'updateable_source'")
            )
        session.flush()

        row = session.execute(
            text(
                "SELECT operation, old_values, new_values FROM audit_log "
                "WHERE table_name = 'data_source' AND record_pk = 'updateable_source' "
                "AND operation = 'update'"
            )
        ).one()
        assert row.operation == "update"
        assert row.old_values["is_active"] is True
        assert row.new_values["is_active"] is False

    def test_soft_delete_is_distinguished_from_ordinary_update(
        self, session: Session, curator_user_id: str
    ) -> None:
        """compound.is_deleted false->true must be logged as soft_delete, not update —
        this is what lets a compliance query distinguish deletions from edits."""
        from .factories import insert_compound, insert_ingestion_snapshot, insert_toolchain

        with audit_context(session, user_id=curator_user_id, reason="setup"):
            source_id = insert_data_source(session, "sd_source")
            snapshot_id = insert_ingestion_snapshot(session, source_id)
            toolchain_id = insert_toolchain(session, "sd_toolchain")
            compound_uid = insert_compound(
                session,
                source_id=source_id,
                snapshot_id=snapshot_id,
                toolchain_id=toolchain_id,
                created_by=curator_user_id,
            )
        session.flush()

        with audit_context(session, user_id=curator_user_id, reason="duplicate of another compound"):
            session.execute(
                text(
                    "UPDATE compound SET is_deleted = true, deleted_reason = 'dup' "
                    "WHERE compound_uid = :uid"
                ),
                {"uid": compound_uid},
            )
        session.flush()

        operations = {
            r[0]
            for r in session.execute(
                text(
                    "SELECT operation FROM audit_log WHERE table_name = 'compound' "
                    "AND record_pk = :uid"
                ),
                {"uid": compound_uid},
            ).all()
        }
        assert "soft_delete" in operations
        # The distinction is the whole point: it must not also be logged as a
        # plain update, or a compliance query could not tell the two apart.
        assert "update" not in operations

    def test_restore_is_distinguished_from_ordinary_update(
        self, session: Session, curator_user_id: str
    ) -> None:
        from .factories import insert_compound, insert_ingestion_snapshot, insert_toolchain

        with audit_context(session, user_id=curator_user_id, reason="setup"):
            source_id = insert_data_source(session, "restore_source")
            snapshot_id = insert_ingestion_snapshot(session, source_id)
            toolchain_id = insert_toolchain(session, "restore_toolchain")
            compound_uid = insert_compound(
                session,
                source_id=source_id,
                snapshot_id=snapshot_id,
                toolchain_id=toolchain_id,
                created_by=curator_user_id,
                is_deleted=True,
                deleted_reason="initially wrong",
            )
        session.flush()

        with audit_context(session, user_id=curator_user_id, reason="restoring — was correct after all"):
            session.execute(
                text(
                    "UPDATE compound SET is_deleted = false, deleted_reason = NULL "
                    "WHERE compound_uid = :uid"
                ),
                {"uid": compound_uid},
            )
        session.flush()

        operations = {
            r[0]
            for r in session.execute(
                text(
                    "SELECT operation FROM audit_log WHERE table_name = 'compound' "
                    "AND record_pk = :uid"
                ),
                {"uid": compound_uid},
            ).all()
        }
        assert "restore" in operations
        # The distinction is the whole point: it must not also be logged as a
        # plain update, or a compliance query could not tell the two apart.
        assert "update" not in operations

    def test_bootstrap_user_exists_and_is_a_service_account(self, session: Session) -> None:
        """Sanity check on migration 0011: the account referenced everywhere as
        SYSTEM_USER_UID must actually exist post-migration."""
        row = session.execute(
            text('SELECT username, role, can_sign FROM "system_user" WHERE user_uid = :uid'),
            {"uid": SYSTEM_USER_UID},
        ).one()
        assert row.username == "system"
        assert row.role == "service"
        assert row.can_sign is False
