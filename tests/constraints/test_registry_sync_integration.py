"""Integration test: registry sync against a real database.

The decision logic (drugsim_db.registry_sync.plan_source_sync) is unit-tested
directly in tests/unit/test_registry_sync.py with no database at all. This file
covers only what that cannot: that apply_source_sync's generated SQL actually
executes against the real schema, and that the audit trigger fires correctly
for data_source writes performed through this path specifically.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_core.ids import SYSTEM_USER_UID
from drugsim_db.audit import audit_context
from drugsim_db.registry_sync import ExistingSource, apply_source_sync, plan_source_sync
from drugsim_quality.license_audit import load_registry

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


def _load_existing(session: Session) -> dict[str, ExistingSource]:
    rows = session.execute(
        text(
            "SELECT source_id, license_spdx, license_tier, is_commercial_ok, "
            "has_sharealike, name, homepage, role, attribution_text, "
            "cadence_days, notes, verification_status FROM data_source"
        )
    ).mappings()
    return {row["source_id"]: ExistingSource(**dict(row)) for row in rows}


class TestFullRegistrySyncAgainstRealSchema:
    """The committed registry.yaml, synced into a freshly migrated (empty) DB."""

    def test_first_sync_inserts_every_source(
        self, session: Session, project_root: object
    ) -> None:
        from pathlib import Path

        registry = load_registry(Path(str(project_root)) / "datasets" / "registry.yaml")
        plan = plan_source_sync(registry, existing=_load_existing(session))
        assert not plan.license_changes

        with audit_context(session, user_id=SYSTEM_USER_UID, reason="initial registry sync"):
            apply_source_sync(session, plan)
        session.flush()

        count = session.execute(text("SELECT count(*) FROM data_source")).scalar_one()
        assert count == len(registry["sources"])

    def test_second_sync_is_a_no_op(self, session: Session, project_root: object) -> None:
        """Syncing an unchanged registry twice must not produce any updates —
        proves the fixed diffing bug (comparing against actual current values,
        not merely field presence) holds against a real database round-trip."""
        from pathlib import Path

        registry = load_registry(Path(str(project_root)) / "datasets" / "registry.yaml")

        with audit_context(session, user_id=SYSTEM_USER_UID, reason="first sync"):
            apply_source_sync(session, plan_source_sync(registry, existing=_load_existing(session)))
        session.flush()

        second_plan = plan_source_sync(registry, existing=_load_existing(session))
        assert not second_plan.to_insert
        assert not second_plan.to_update
        assert not second_plan.license_changes
        assert len(second_plan.unchanged) == len(registry["sources"])

    def test_audit_log_records_each_insert(self, session: Session, project_root: object) -> None:
        from pathlib import Path

        registry = load_registry(Path(str(project_root)) / "datasets" / "registry.yaml")

        with audit_context(session, user_id=SYSTEM_USER_UID, reason="audited sync"):
            apply_source_sync(session, plan_source_sync(registry, existing=_load_existing(session)))
        session.flush()

        audit_count = session.execute(
            text(
                "SELECT count(*) FROM audit_log WHERE table_name = 'data_source' "
                "AND operation = 'insert' AND change_reason = 'audited sync'"
            )
        ).scalar_one()
        assert audit_count == len(registry["sources"])
