"""Tests for per-record licence resolution.

The property that matters most: a source missing from the registry, or
missing a required licence field, resolves as ``unresolved`` — it is never
treated as permitted by default. This is the "fail closed" contract.
"""

from __future__ import annotations

import pytest

from drugsim_curation.provenance import SourceRegistry, resolve_license

pytestmark = pytest.mark.unit


def _registry(sources: list[dict]) -> SourceRegistry:
    return SourceRegistry({"sources": sources})


class TestResolvedSource:
    def test_a_complete_licence_block_resolves(self) -> None:
        registry = _registry(
            [
                {
                    "source_id": "chembl",
                    "license": {
                        "spdx": "CC-BY-SA-3.0",
                        "tier": "red",
                        "commercial_ok": True,
                        "attribution": "ChEMBL (EMBL-EBI)",
                    },
                }
            ]
        )
        result = resolve_license(registry, "chembl")
        assert result.license_status == "resolved"
        assert result.spdx == "CC-BY-SA-3.0"
        assert result.commercial_ok is True
        assert result.reason is None


class TestFailsClosed:
    def test_unknown_source_id_is_unresolved(self) -> None:
        registry = _registry([{"source_id": "chembl", "license": {"spdx": "X", "tier": "red", "commercial_ok": True}}])
        result = resolve_license(registry, "some_source_not_in_registry")
        assert result.license_status == "unresolved"
        assert result.commercial_ok is None
        assert "not found" in result.reason

    def test_missing_license_block_is_unresolved(self) -> None:
        registry = _registry([{"source_id": "chembl"}])
        result = resolve_license(registry, "chembl")
        assert result.license_status == "unresolved"

    def test_missing_commercial_ok_is_unresolved_not_assumed_true(self) -> None:
        registry = _registry([{"source_id": "chembl", "license": {"spdx": "X", "tier": "red"}}])
        result = resolve_license(registry, "chembl")
        assert result.license_status == "unresolved"
        assert result.commercial_ok is None

    def test_excluded_sources_section_does_not_resolve(self) -> None:
        # Only `sources` (active) resolves -- a source deliberately listed
        # under excluded_sources must never silently resolve as usable.
        registry = SourceRegistry(
            {
                "sources": [],
                "excluded_sources": [
                    {"source_id": "drugbank", "license": {"spdx": "X", "tier": "black", "commercial_ok": False}}
                ],
            }
        )
        result = resolve_license(registry, "drugbank")
        assert result.license_status == "unresolved"
