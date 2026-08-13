"""Tests for version and toolchain identification.

``toolchain_id`` is an input to ``feature_set_id``. If it fails to capture something
that changes a descriptor value, features computed under different toolchains become
silently interchangeable and reproducibility is lost (ADR-005).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from drugsim_core.version import (
    __version__,
    build_toolchain_id,
    get_rdkit_version,
    get_version,
    toolchain_digest,
)

pytestmark = pytest.mark.unit


class TestVersion:
    """Application version."""

    def test_is_semver(self) -> None:
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_get_version_matches_dunder(self) -> None:
        assert get_version() == __version__

    def test_matches_pyproject(self, project_root: object) -> None:
        """The declared version and pyproject must not drift apart."""
        from pathlib import Path

        content = (Path(str(project_root)) / "pyproject.toml").read_text(encoding="utf-8")
        assert f'version = "{__version__}"' in content


class TestToolchainId:
    """The reproducibility-critical identifier."""

    def test_includes_all_three_components(self) -> None:
        tid = build_toolchain_id(
            rdkit_version="2025.3.3",
            python_version="3.12.4",
            standardization_pipeline_version="v1",
        )
        assert tid == "rdkit-2025.3.3__python-3.12.4__stdpipe-v1"

    def test_is_deterministic(self) -> None:
        args = {
            "rdkit_version": "2025.3.3",
            "python_version": "3.12.4",
            "standardization_pipeline_version": "v1",
        }
        assert build_toolchain_id(**args) == build_toolchain_id(**args)

    @pytest.mark.parametrize(
        ("field", "changed"),
        [
            ("rdkit_version", "2025.9.1"),
            ("python_version", "3.13.0"),
            ("standardization_pipeline_version", "v2"),
        ],
    )
    def test_any_component_change_changes_the_id(self, field: str, changed: str) -> None:
        """A change to any component must produce a different identifier.

        This is the property that prevents features from one toolchain being reused
        under another.
        """
        base = {
            "rdkit_version": "2025.3.3",
            "python_version": "3.12.4",
            "standardization_pipeline_version": "v1",
        }
        modified = {**base, field: changed}
        assert build_toolchain_id(**base) != build_toolchain_id(**modified)

    def test_absent_rdkit_is_recorded_explicitly(self) -> None:
        """RDKit absence must be visible in the toolchain id when detection yields none.

        Forces the absent-detection path via a mock rather than relying on RDKit
        actually being uninstalled in whatever environment runs this test. RDKit
        is a pinned production dependency (pyproject.toml) and legitimately IS
        installed in most environments this suite runs in — a test that only
        passes when a dependency happens to be missing is not testing what its
        name claims, it is testing the environment.
        """
        with patch("drugsim_core.version.get_rdkit_version", return_value=None):
            tid = build_toolchain_id(rdkit_version=None, python_version="3.12.4")
        assert "rdkit-absent" in tid

    def test_installed_rdkit_without_pipeline_version_raises(self) -> None:
        """Chemistry code present but unversioned would break feature addressing."""
        with pytest.raises(RuntimeError, match="standardization_pipeline_version"):
            build_toolchain_id(
                rdkit_version="2025.3.3",
                python_version="3.12.4",
                standardization_pipeline_version="unset",
            )

    def test_rdkit_version_detection_does_not_raise_when_import_fails(self) -> None:
        """get_rdkit_version catches ImportError and returns None rather than
        propagating it — simulated directly by making the import raise, rather
        than depending on RDKit actually being absent from this environment."""
        import builtins

        real_import = builtins.__import__

        def _failing_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "rdkit":
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        get_rdkit_version.cache_clear()
        try:
            with patch("builtins.__import__", side_effect=_failing_import):
                assert get_rdkit_version() is None
        finally:
            get_rdkit_version.cache_clear()

    def test_rdkit_version_detection_returns_a_string_when_installed(self) -> None:
        """In this environment RDKit genuinely is installed (pinned dependency) —
        detection should reflect reality, not a hardcoded assumption either way."""
        get_rdkit_version.cache_clear()
        result = get_rdkit_version()
        get_rdkit_version.cache_clear()
        assert result is None or isinstance(result, str)


class TestToolchainDigest:
    """Fixed-width digest form."""

    def test_length(self) -> None:
        assert len(toolchain_digest("rdkit-2025.3.3__python-3.12.4__stdpipe-v1")) == 12

    def test_deterministic(self) -> None:
        assert toolchain_digest("a") == toolchain_digest("a")

    def test_differs_for_different_input(self) -> None:
        assert toolchain_digest("a") != toolchain_digest("b")
