"""Tests for the dataset licence audit (rules LC-01 … LC-06).

The audit is a required CI gate. These tests pin both directions: that real
violations fail, and that the committed registry passes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from drugsim_quality.license_audit import (
    TIER_BY_SPDX,
    LicenseTier,
    audit_registry,
    build_attribution_manifest,
    load_registry,
)

pytestmark = pytest.mark.unit


def _source(**licence: Any) -> dict[str, Any]:
    """Build a minimal registry containing one source with the given licence."""
    return {"sources": [{"source_id": "test_source", "name": "Test", "license": licence}]}


class TestTierMapping:
    """The normative SPDX-to-tier mapping."""

    @pytest.mark.parametrize(
        ("spdx", "tier"),
        [
            ("CC0-1.0", LicenseTier.GREEN),
            ("US-PD", LicenseTier.GREEN),
            ("CC-BY-4.0", LicenseTier.AMBER),
            ("CC-BY-3.0", LicenseTier.AMBER),
            ("CC-BY-SA-4.0", LicenseTier.RED),
            ("CC-BY-SA-3.0", LicenseTier.RED),
            ("CC-BY-NC-SA-4.0", LicenseTier.BLACK),
            ("PROPRIETARY", LicenseTier.BLACK),
        ],
    )
    def test_mapping_matches_phase1(self, spdx: str, tier: LicenseTier) -> None:
        """The mapping must match Phase 1 data dictionary §C.2."""
        assert TIER_BY_SPDX[spdx] == tier

    def test_sharealike_licences_are_red(self) -> None:
        """Every ShareAlike licence carries the copyleft exposure flagged as risk R1."""
        for spdx, tier in TIER_BY_SPDX.items():
            if "SA" in spdx and "NC" not in spdx:
                assert tier == LicenseTier.RED, spdx

    def test_noncommercial_licences_are_black(self) -> None:
        for spdx, tier in TIER_BY_SPDX.items():
            if "NC" in spdx:
                assert tier == LicenseTier.BLACK, spdx


class TestRuleViolations:
    """Each rule must actually fail on a violating registry."""

    def test_lc01_missing_license_block(self) -> None:
        result = audit_registry({"sources": [{"source_id": "x", "name": "X"}]})
        assert not result.passed
        assert any("LC-01" in e for e in result.errors)

    def test_lc01_missing_spdx(self) -> None:
        result = audit_registry(_source(tier="green"))
        assert not result.passed
        assert any("no SPDX identifier" in e for e in result.errors)

    def test_lc02_tier_contradicts_spdx(self) -> None:
        """Declaring ChEMBL's CC BY-SA 3.0 as amber would hide copyleft exposure."""
        result = audit_registry(
            _source(spdx="CC-BY-SA-3.0", tier="amber", attribution="x")
        )
        assert not result.passed
        assert any("LC-02" in e and "contradicts" in e for e in result.errors)

    def test_lc02_unknown_spdx_rejected(self) -> None:
        """An unmapped licence must fail rather than default to permissive."""
        result = audit_registry(_source(spdx="WTFPL", tier="green"))
        assert not result.passed
        assert any("not in the normative tier mapping" in e for e in result.errors)

    def test_lc03_commercial_flag_contradicts_tier(self) -> None:
        result = audit_registry(
            _source(spdx="CC-BY-NC-SA-4.0", tier="black", commercial_ok=True)
        )
        assert not result.passed
        assert any("LC-03" in e for e in result.errors)

    def test_lc02_sharealike_under_declared(self) -> None:
        """Under-declaring ShareAlike is the dangerous direction."""
        result = audit_registry(
            _source(spdx="CC-BY-SA-4.0", tier="red", sharealike=False, attribution="x")
        )
        assert not result.passed
        assert any("sharealike" in e for e in result.errors)

    def test_lc05_attribution_required_for_cc_by(self) -> None:
        result = audit_registry(_source(spdx="CC-BY-4.0", tier="amber"))
        assert not result.passed
        assert any("LC-05" in e for e in result.errors)

    def test_lc05_attribution_not_required_for_cc0(self) -> None:
        result = audit_registry(_source(spdx="CC0-1.0", tier="green"))
        assert result.passed

    def test_lc01_mixed_without_enumeration(self) -> None:
        result = audit_registry(_source(spdx="MIXED", tier="mixed"))
        assert not result.passed
        assert any("enumerates neither" in e for e in result.errors)

    def test_lc03_exclusion_must_be_black(self) -> None:
        """FreeSolv-shaped carve-outs must be black-tier and non-commercial."""
        result = audit_registry(
            _source(
                spdx="MIXED",
                tier="mixed",
                default_spdx="CC-BY-4.0",
                default_tier="amber",
                attribution="x",
                exclusions=[{"dataset": "freesolv", "tier": "amber", "commercial_ok": True}],
            )
        )
        assert not result.passed
        assert any("must be black-tier" in e for e in result.errors)

    def test_lc06_excluded_source_without_reason(self) -> None:
        result = audit_registry(
            {"sources": [], "excluded_sources": [{"source_id": "drugbank", "license": {}}]}
        )
        assert not result.passed
        assert any("excluded without a recorded reason" in e for e in result.errors)


class TestValidShapes:
    """Both legitimate mixed-licensing shapes must pass."""

    def test_split_licensing_portions(self) -> None:
        """BindingDB shape: internally split, no single default."""
        result = audit_registry(
            _source(
                spdx="MIXED",
                tier="mixed",
                split_licensing=[
                    {
                        "portion": "curated",
                        "spdx": "CC-BY-3.0",
                        "tier": "amber",
                        "sharealike": False,
                        "attribution": "a",
                    },
                    {
                        "portion": "derived",
                        "spdx": "CC-BY-SA-3.0",
                        "tier": "red",
                        "sharealike": True,
                        "attribution": "b",
                    },
                ],
            )
        )
        assert result.passed, result.errors

    def test_default_plus_exclusions(self) -> None:
        """TDC shape: uniform default with a non-commercial carve-out."""
        result = audit_registry(
            _source(
                spdx="MIXED",
                tier="mixed",
                default_spdx="CC-BY-4.0",
                default_tier="amber",
                attribution="Therapeutics Data Commons",
                exclusions=[
                    {
                        "dataset": "freesolv",
                        "spdx": "CC-BY-NC-SA-4.0",
                        "tier": "black",
                        "commercial_ok": False,
                    }
                ],
            )
        )
        assert result.passed, result.errors


class TestCommittedRegistry:
    """The real registry must satisfy its own rules."""

    @pytest.fixture
    def registry(self, project_root: Path) -> dict[str, Any]:
        return load_registry(project_root / "datasets" / "registry.yaml")

    def test_committed_registry_passes(self, registry: dict[str, Any]) -> None:
        result = audit_registry(registry)
        assert result.passed, "\n".join(result.errors)

    def test_all_tier_1_sources_present(self, registry: dict[str, Any]) -> None:
        """The nine Tier 1 sources selected in Phase 1 Step 1 must be registered."""
        ids = {s["source_id"] for s in registry["sources"]}
        expected = {
            "chembl", "pubchem", "bindingdb", "tdc", "toxcast_tox21",
            "uniprot", "pdb", "drugcentral", "opentargets",
        }
        assert expected <= ids, f"missing: {expected - ids}"

    def test_drugbank_is_excluded(self, registry: dict[str, Any]) -> None:
        """DrugBank requires a commercial licence and must stay excluded."""
        excluded = {s["source_id"] for s in registry.get("excluded_sources", [])}
        assert "drugbank" in excluded

    def test_freesolv_is_excluded(self, registry: dict[str, Any]) -> None:
        """FreeSolv is CC BY-NC-SA 4.0 and ships inside TDC's uniform interface."""
        excluded = {s["source_id"] for s in registry.get("excluded_sources", [])}
        assert "freesolv" in excluded

    def test_bindingdb_declares_split_licensing(self, registry: dict[str, Any]) -> None:
        """The source that makes per-record licence tracking mandatory (ADR-007)."""
        bindingdb = next(s for s in registry["sources"] if s["source_id"] == "bindingdb")
        portions = bindingdb["license"]["split_licensing"]
        spdx = {p["spdx"] for p in portions}
        assert spdx == {"CC-BY-3.0", "CC-BY-SA-3.0"}

    def test_tdc_records_missing_unit_documentation(self, registry: dict[str, Any]) -> None:
        """TDC's undocumented units drive the empirical protocol at gate G4."""
        tdc = next(s for s in registry["sources"] if s["source_id"] == "tdc")
        assert tdc["units_documented"] is False

    def test_stale_sources_are_flagged(self, registry: dict[str, Any]) -> None:
        """DrugCentral's slowed cadence must surface as a warning, not silence."""
        result = audit_registry(registry)
        assert any("drugcentral" in w for w in result.warnings)


class TestAttributionManifest:
    """Manifest generation (LC-05)."""

    def test_includes_attribution_text(self, project_root: Path) -> None:
        registry = load_registry(project_root / "datasets" / "registry.yaml")
        manifest = build_attribution_manifest(registry)
        assert "ChEMBL" in manifest
        assert "CC-BY-SA-3.0" in manifest
        assert "UniProt" in manifest

    def test_groups_by_tier(self, project_root: Path) -> None:
        registry = load_registry(project_root / "datasets" / "registry.yaml")
        manifest = build_attribution_manifest(registry)
        assert "## Tier: green" in manifest
        assert "## Tier: red" in manifest


class TestRegistryLoading:
    """Loader validation."""

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="not found"):
            load_registry(tmp_path / "absent.yaml")

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "r.yaml"
        path.write_text("- a\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must be a mapping"):
            load_registry(path)

    def test_missing_sources_key_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "r.yaml"
        path.write_text("other: 1\n", encoding="utf-8")
        with pytest.raises(ValueError, match="no 'sources' key"):
            load_registry(path)
