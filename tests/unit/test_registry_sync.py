"""Tests for the pure registry-sync planning logic.

No database involved — plan_source_sync takes plain data in and returns a plain
plan out. This is deliberate (drugsim_db.registry_sync module docstring): it
lets the decision logic that is actually likely to contain a bug be tested
directly, leaving only a thin, largely mechanical I/O layer to be verified
against a real database (deferred — see Sprint 2.3 notes).
"""

from __future__ import annotations

import pytest

from unittest.mock import MagicMock

from drugsim_core.errors import LicenseViolationError
from drugsim_db.registry_sync import (
    _SAFE_TO_AUTO_UPDATE,
    ExistingSource,
    LicenseChange,
    SourceSyncPlan,
    apply_source_sync,
    plan_source_sync,
)

pytestmark = pytest.mark.unit


def _entry(source_id: str, spdx: str, tier: str, **overrides: object) -> dict[str, object]:
    """Build a minimal registry source entry."""
    license_block = {"spdx": spdx, "tier": tier, "commercial_ok": tier != "black", "sharealike": tier == "red"}
    license_block.update(overrides.pop("license_overrides", {}))
    return {
        "source_id": source_id,
        "name": source_id.title(),
        "homepage": f"https://{source_id}.test",
        "role": "test",
        "license": license_block,
        "verification": {"status": "verified", "date": "2026-08-06"},
        **overrides,
    }


class TestNewSources:
    """A source in the registry but not in the database is an insert."""

    def test_single_new_source(self) -> None:
        registry = {"sources": [_entry("chembl", "CC-BY-SA-4.0", "red")]}
        plan = plan_source_sync(registry, existing={})
        assert len(plan.to_insert) == 1
        assert plan.to_insert[0]["source_id"] == "chembl"
        assert plan.to_insert[0]["license_tier"] == "red"
        assert not plan.to_update
        assert not plan.license_changes
        assert not plan.unchanged

    def test_commercial_ok_defaults_from_tier_when_absent(self) -> None:
        entry = _entry("x", "CC0-1.0", "green")
        del entry["license"]["commercial_ok"]  # type: ignore[index]
        plan = plan_source_sync({"sources": [entry]}, existing={})
        assert plan.to_insert[0]["is_commercial_ok"] is True

    def test_multiple_new_sources_all_captured(self) -> None:
        registry = {
            "sources": [
                _entry("chembl", "CC-BY-SA-4.0", "red"),
                _entry("pdb", "CC0-1.0", "green"),
                _entry("uniprot", "CC-BY-4.0", "amber"),
            ]
        }
        plan = plan_source_sync(registry, existing={})
        assert {s["source_id"] for s in plan.to_insert} == {"chembl", "pdb", "uniprot"}


class TestUnchangedSources:
    """A source matching existing DB state needs no action."""

    def test_identical_source_is_unchanged(self) -> None:
        """`existing` must match EVERY field _extract_source_fields would derive
        from the entry, not just the license fields — otherwise this test would
        pass for the wrong reason (comparing against defaults, not real values)."""
        registry = {"sources": [_entry("pdb", "CC0-1.0", "green")]}
        existing = {
            "pdb": ExistingSource(
                source_id="pdb", license_spdx="CC0-1.0", license_tier="green",
                is_commercial_ok=True, has_sharealike=False,
                name="Pdb", homepage="https://pdb.test", role="test",
                attribution_text="", cadence_days=None, notes=None,
                verification_status="verified",
            )
        }
        plan = plan_source_sync(registry, existing)
        assert plan.unchanged == ["pdb"]
        assert not plan.to_insert
        assert not plan.to_update
        assert not plan.license_changes


class TestSafeUpdates:
    """Cosmetic/operational fields update automatically."""

    def test_homepage_change_is_a_safe_update(self) -> None:
        """Every other field matches current state, isolating homepage as the
        single detected change — proves the diff is field-by-field, not
        all-or-nothing."""
        registry = {"sources": [_entry("pdb", "CC0-1.0", "green", homepage="https://new.rcsb.org")]}
        existing = {
            "pdb": ExistingSource(
                source_id="pdb", license_spdx="CC0-1.0", license_tier="green",
                is_commercial_ok=True, has_sharealike=False,
                name="Pdb", homepage="https://pdb.test", role="test",
                attribution_text="", cadence_days=None, notes=None,
                verification_status="verified",
            )
        }
        plan = plan_source_sync(registry, existing)
        assert len(plan.to_update) == 1
        source_id, changed = plan.to_update[0]
        assert source_id == "pdb"
        assert changed == {"homepage": "https://new.rcsb.org"}

    def test_safe_update_never_touches_license_fields(self) -> None:
        assert "license_spdx" not in _SAFE_TO_AUTO_UPDATE
        assert "license_tier" not in _SAFE_TO_AUTO_UPDATE
        assert "is_commercial_ok" not in _SAFE_TO_AUTO_UPDATE


class TestLicenseChangeDetection:
    """Rule LC-04: a relicensing event is flagged, never silently applied."""

    def test_spdx_change_is_flagged_not_applied(self) -> None:
        registry = {"sources": [_entry("drugcentral", "CC-BY-NC-4.0", "black")]}
        existing = {
            "drugcentral": ExistingSource(
                source_id="drugcentral", license_spdx="CC-BY-SA-4.0", license_tier="red",
                is_commercial_ok=True, has_sharealike=True,
            )
        }
        plan = plan_source_sync(registry, existing)
        assert len(plan.license_changes) == 1
        change = plan.license_changes[0]
        assert change.old_spdx == "CC-BY-SA-4.0"
        assert change.new_spdx == "CC-BY-NC-4.0"
        assert change.old_tier == "red"
        assert change.new_tier == "black"
        assert not plan.to_insert
        assert not plan.to_update
        assert not plan.is_safe_to_apply

    def test_tier_only_change_is_also_flagged(self) -> None:
        """Even if SPDX text is unchanged, a tier mismatch alone is material."""
        registry = {"sources": [_entry("x", "CC-BY-4.0", "amber")]}
        existing = {
            "x": ExistingSource(
                source_id="x", license_spdx="CC-BY-4.0", license_tier="green",
                is_commercial_ok=True, has_sharealike=False,
            )
        }
        plan = plan_source_sync(registry, existing)
        assert len(plan.license_changes) == 1

    def test_plan_with_no_license_changes_is_safe(self) -> None:
        plan = SourceSyncPlan(to_insert=[{"source_id": "x"}])
        assert plan.is_safe_to_apply


class TestInternalConsistencyCheck:
    """_extract_source_fields independently re-validates tier-vs-SPDX, as a
    second check alongside the standalone license_audit script."""

    def test_inconsistent_tier_raises(self) -> None:
        entry = _entry("bad", "CC-BY-SA-4.0", "amber")  # SA-4.0 should be red
        with pytest.raises(LicenseViolationError, match="maps to 'red'"):
            plan_source_sync({"sources": [entry]}, existing={})

    def test_missing_spdx_raises(self) -> None:
        entry = _entry("bad", "CC0-1.0", "green")
        del entry["license"]["spdx"]  # type: ignore[index]
        with pytest.raises(LicenseViolationError, match="no license.spdx"):
            plan_source_sync({"sources": [entry]}, existing={})

    def test_mixed_spdx_skips_tier_cross_check(self) -> None:
        """MIXED sources (BindingDB, TDC) have no single tier to cross-check against
        the SPDX-to-tier table — their consistency is checked at the portion level
        by drugsim_quality.license_audit instead."""
        entry = _entry("bindingdb", "MIXED", "mixed")
        plan = plan_source_sync({"sources": [entry]}, existing={})
        assert plan.to_insert[0]["is_split_licensed"] is True


class TestApplyRefusesUnacknowledgedLicenseChanges:
    """apply_source_sync must not silently apply a licence change."""

    def test_apply_raises_without_acknowledgement(self) -> None:
        plan = SourceSyncPlan(
            license_changes=[
                LicenseChange(
                    source_id="x", old_spdx="CC-BY-4.0", new_spdx="CC-BY-NC-4.0",
                    old_tier="amber", new_tier="black",
                )
            ]
        )
        session = MagicMock()
        with pytest.raises(LicenseViolationError, match="require human review"):
            apply_source_sync(session, plan)
        session.execute.assert_not_called()

    def test_apply_proceeds_with_acknowledgement(self) -> None:
        plan = SourceSyncPlan(
            license_changes=[
                LicenseChange(source_id="x", old_spdx="a", new_spdx="b", old_tier="amber", new_tier="black")
            ]
        )
        session = MagicMock()
        apply_source_sync(session, plan, acknowledge_license_changes=True)
        # No inserts/updates in this plan, so no SQL should have been issued —
        # but critically, no exception was raised either.
        session.execute.assert_not_called()

    def test_apply_issues_insert_for_new_sources(self) -> None:
        plan = SourceSyncPlan(to_insert=[{"source_id": "x", "name": "X"}])
        session = MagicMock()
        apply_source_sync(session, plan)
        assert session.execute.call_count == 1
        sql_text = str(session.execute.call_args.args[0])
        assert "INSERT INTO data_source" in sql_text

    def test_apply_issues_update_for_changed_sources(self) -> None:
        plan = SourceSyncPlan(to_update=[("x", {"homepage": "https://new.test"})])
        session = MagicMock()
        apply_source_sync(session, plan)
        sql_text = str(session.execute.call_args.args[0])
        assert "UPDATE data_source" in sql_text


class TestRealRegistryProducesAValidPlan:
    """The committed registry.yaml, planned against an empty database, must
    produce only inserts — no license changes, no crashes."""

    def test_full_registry_plans_cleanly(self, project_root: object) -> None:
        from pathlib import Path

        from drugsim_quality.license_audit import load_registry

        registry = load_registry(Path(str(project_root)) / "datasets" / "registry.yaml")
        plan = plan_source_sync(registry, existing={})

        assert not plan.license_changes
        assert len(plan.to_insert) == len(registry["sources"])
        for fields in plan.to_insert:
            assert fields["license_tier"] in {"green", "amber", "red", "black", "mixed"}
