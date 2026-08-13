"""Constraint tests: governance domain.

Each test proves a violating insert FAILS. This is the point of this whole
directory (TDS §9.3): a migration that silently drops one of these CHECKs would
pass every functional test, because the system would still work — it would
simply no longer prevent what the constraint prevented.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from drugsim_core.ids import SYSTEM_USER_UID, generate_ulid
from drugsim_db.audit import audit_context

from .factories import insert_data_source

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


class TestDataSourceLicenseTierConsistency:
    """ck_ds_tier_commercial / ck_ds_tier_sharealike.

    These are the database-level backstop for the LC-02/LC-03 rules the Python
    licence audit (drugsim_quality.license_audit) already checks against the
    registry file — belt and braces, since a row could in principle be inserted
    by a path that bypasses the Python audit.
    """

    def test_black_tier_must_be_commercially_prohibited(self, session: Session) -> None:
        with pytest.raises(IntegrityError, match="ck_ds_tier_commercial"):
            session.execute(
                text(
                    "INSERT INTO data_source (source_id, name, homepage, role, "
                    "license_spdx, license_tier, is_commercial_ok, has_sharealike, "
                    "attribution_text, verification_status, verification_date) "
                    "VALUES ('bad', 'Bad', 'https://x', 'test', 'CC-BY-NC-4.0', "
                    "'black', true, false, 'x', 'verified', now())"
                )
            )
            session.flush()

    def test_non_black_tier_cannot_be_commercially_prohibited(self, session: Session) -> None:
        with pytest.raises(IntegrityError, match="ck_ds_tier_commercial"):
            session.execute(
                text(
                    "INSERT INTO data_source (source_id, name, homepage, role, "
                    "license_spdx, license_tier, is_commercial_ok, has_sharealike, "
                    "attribution_text, verification_status, verification_date) "
                    "VALUES ('bad2', 'Bad', 'https://x', 'test', 'CC-BY-4.0', "
                    "'amber', false, false, 'x', 'verified', now())"
                )
            )
            session.flush()

    def test_red_tier_must_declare_sharealike(self, session: Session) -> None:
        with pytest.raises(IntegrityError, match="ck_ds_tier_sharealike"):
            session.execute(
                text(
                    "INSERT INTO data_source (source_id, name, homepage, role, "
                    "license_spdx, license_tier, is_commercial_ok, has_sharealike, "
                    "attribution_text, verification_status, verification_date) "
                    "VALUES ('bad3', 'Bad', 'https://x', 'test', 'CC-BY-SA-4.0', "
                    "'red', true, false, 'x', 'verified', now())"
                )
            )
            session.flush()

    def test_valid_row_succeeds(self, session: Session) -> None:
        insert_data_source(session, "good_source", tier="green", commercial_ok=True, sharealike=False)
        session.flush()  # must not raise


class TestSystemUserDeactivation:
    """ck_user_deactivation: a user can only be deactivated, never deleted (P8)."""

    def test_inactive_user_without_deactivated_at_rejected(self, session: Session) -> None:
        with pytest.raises(IntegrityError, match="ck_user_deactivation"):
            session.execute(
                text(
                    "INSERT INTO system_user (user_uid, username, full_name, email, "
                    "role, is_active) VALUES (:uid, 'x', 'X', 'x@test', 'curator', false)"
                ),
                {"uid": generate_ulid()},
            )
            session.flush()

    def test_active_user_without_deactivated_at_succeeds(self, session: Session) -> None:
        session.execute(
            text(
                "INSERT INTO system_user (user_uid, username, full_name, email, role) "
                "VALUES (:uid, 'x2', 'X', 'x2@test', 'curator')"
            ),
            {"uid": generate_ulid()},
        )
        session.flush()

    def test_deactivation_via_update_requires_timestamp(self, session: Session, curator_user_id: str) -> None:
        with pytest.raises(IntegrityError, match="ck_user_deactivation"):
            with audit_context(session, user_id=SYSTEM_USER_UID, reason="test"):
                session.execute(
                    text("UPDATE system_user SET is_active = false WHERE user_uid = :uid"),
                    {"uid": curator_user_id},
                )
            session.flush()


class TestHardDeletesAreImpossible:
    """P8 as a grant, not a convention: UPDATE/DELETE are revoked on audit_log."""

    def test_delete_on_audit_log_is_revoked(self, session: Session, curator_user_id: str) -> None:
        with pytest.raises(Exception, match="permission denied"):
            session.execute(text("DELETE FROM audit_log"))
            session.flush()

    def test_update_on_audit_log_is_revoked(self, session: Session) -> None:
        with pytest.raises(Exception, match="permission denied"):
            session.execute(text("UPDATE audit_log SET change_reason = 'tampered'"))
            session.flush()


class TestElectronicSignatureUniqueness:
    """uq_sig: one signature per (record, signer, meaning)."""

    def test_duplicate_signature_rejected(self, session: Session, curator_user_id: str) -> None:
        payload = {
            "uid1": generate_ulid(),
            "uid2": generate_ulid(),
            "signer": curator_user_id,
            "hash": "a" * 64,
        }
        session.execute(
            text(
                "INSERT INTO electronic_signature (signature_uid, signed_table, "
                "signed_record_pk, record_hash, signer_uid, signature_meaning, "
                "signature_text) VALUES (:uid1, 'ich_m7_assessment', 'rec1', :hash, "
                ":signer, 'approval', 'I approve')"
            ),
            payload,
        )
        session.flush()

        with pytest.raises(IntegrityError, match="uq_sig"):
            session.execute(
                text(
                    "INSERT INTO electronic_signature (signature_uid, signed_table, "
                    "signed_record_pk, record_hash, signer_uid, signature_meaning, "
                    "signature_text) VALUES (:uid2, 'ich_m7_assessment', 'rec1', :hash, "
                    ":signer, 'approval', 'I approve again')"
                ),
                payload,
            )
            session.flush()
