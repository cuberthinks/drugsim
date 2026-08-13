"""Tests for layered configuration and its production safety invariants."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from drugsim_core.config import Environment, Settings, build_settings, load_yaml_config

pytestmark = pytest.mark.unit


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Create a minimal on-disk configuration tree."""
    (tmp_path / "environments").mkdir()
    (tmp_path / "base.yaml").write_text(
        yaml.safe_dump({"log_level": "INFO", "database_name": "drugsim"}),
        encoding="utf-8",
    )
    (tmp_path / "environments" / "local.yaml").write_text(
        yaml.safe_dump({"log_format": "console", "debug": True}),
        encoding="utf-8",
    )
    return tmp_path


class TestLoadYaml:
    """YAML loading behaviour."""

    def test_missing_file_yields_empty_mapping(self, tmp_path: Path) -> None:
        """Optional per-environment overlays need not exist."""
        assert load_yaml_config(tmp_path / "absent.yaml") == {}

    def test_empty_file_yields_empty_mapping(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.yaml"
        path.write_text("", encoding="utf-8")
        assert load_yaml_config(path) == {}

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "list.yaml"
        path.write_text("- a\n- b\n", encoding="utf-8")
        with pytest.raises(ValueError, match="must contain a mapping"):
            load_yaml_config(path)


class TestPrecedence:
    """Layer precedence: defaults < base < environment < env vars < overrides."""

    def test_environment_overlay_beats_base(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRUGSIM_ENVIRONMENT", "local")
        settings = build_settings(config_dir=config_dir)
        assert settings.log_format == "console"   # from local.yaml
        assert settings.log_level == "INFO"       # from base.yaml

    def test_env_var_beats_yaml(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRUGSIM_ENVIRONMENT", "local")
        monkeypatch.setenv("DRUGSIM_LOG_LEVEL", "WARNING")
        assert build_settings(config_dir=config_dir).log_level == "WARNING"

    def test_explicit_override_beats_all(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DRUGSIM_ENVIRONMENT", "local")
        settings = build_settings(config_dir=config_dir, database_name="override")
        assert settings.database_name == "override"

    def test_unknown_environment_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DRUGSIM_ENVIRONMENT", "moon_base")
        with pytest.raises(ValueError, match="unknown environment"):
            build_settings()


class TestProductionInvariants:
    """Settings that would be unsafe in a production-like environment."""

    def test_debug_rejected_in_production(self) -> None:
        """Debug output can include payloads — the path by which a structure leaks."""
        with pytest.raises(ValueError, match="debug must be false"):
            Settings(environment=Environment.PRODUCTION, debug=True)

    def test_debug_rejected_in_staging(self) -> None:
        with pytest.raises(ValueError, match="debug must be false"):
            Settings(environment=Environment.STAGING, debug=True)

    def test_console_logging_rejected_in_production(self) -> None:
        with pytest.raises(ValueError, match="log_format must be 'json'"):
            Settings(environment=Environment.PRODUCTION, log_format="console")

    def test_debug_permitted_locally(self) -> None:
        assert Settings(environment=Environment.LOCAL, debug=True).debug

    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            (Environment.LOCAL, False),
            (Environment.DEVELOPMENT, False),
            (Environment.TEST, False),
            (Environment.STAGING, True),
            (Environment.PRODUCTION, True),
        ],
    )
    def test_is_production_like(self, env: Environment, expected: bool) -> None:
        assert env.is_production_like is expected


class TestValidation:
    """Field validation."""

    def test_log_level_is_normalised(self) -> None:
        assert Settings(log_level="debug").log_level == "DEBUG"

    def test_invalid_log_level_rejected(self) -> None:
        with pytest.raises(ValueError, match="log_level must be one of"):
            Settings(log_level="chatty")

    def test_invalid_log_format_rejected(self) -> None:
        with pytest.raises(ValueError, match="log_format must be"):
            Settings(log_format="xml")

    def test_port_range_enforced(self) -> None:
        with pytest.raises(ValueError, match="less than or equal to 65535"):
            Settings(database_port=70000)

    def test_unknown_field_rejected(self) -> None:
        """extra='forbid' catches typos in configuration keys."""
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            Settings(databse_name="typo")


class TestSecrets:
    """Secret handling."""

    def test_password_is_not_in_repr(self) -> None:
        """SecretStr keeps the value out of accidental prints and tracebacks."""
        settings = Settings(database_password="hunter2")
        assert "hunter2" not in repr(settings)
        assert "hunter2" not in str(settings.database_password)

    def test_database_url_reveals_password(self) -> None:
        settings = Settings(database_password="hunter2", database_user="u")
        assert "hunter2" in settings.database_url

    def test_no_secrets_in_committed_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "base.yaml").write_text(
            yaml.safe_dump({"log_level": "INFO"}), encoding="utf-8"
        )
        Settings.assert_no_secrets_in_yaml(tmp_path)  # must not raise

    def test_secret_in_yaml_is_rejected(self, tmp_path: Path) -> None:
        """A committed secret is disclosed the moment the repo is cloned."""
        (tmp_path / "base.yaml").write_text(
            yaml.safe_dump({"database_password": "oops"}), encoding="utf-8"
        )
        with pytest.raises(ValueError, match="secret-bearing fields found"):
            Settings.assert_no_secrets_in_yaml(tmp_path)


class TestRealConfigTree:
    """The committed config/ directory must satisfy its own rules."""

    def test_committed_config_has_no_secrets(self) -> None:
        config_root = Path(__file__).resolve().parents[2] / "config"
        Settings.assert_no_secrets_in_yaml(config_root)

    @pytest.mark.parametrize(
        "env", ["local", "development", "test", "staging", "production"]
    )
    def test_every_environment_overlay_exists_and_parses(self, env: str) -> None:
        path = Path(__file__).resolve().parents[2] / "config" / "environments" / f"{env}.yaml"
        assert path.exists(), f"missing overlay for {env}"
        assert isinstance(load_yaml_config(path), dict)

    @pytest.mark.parametrize("env", ["staging", "production"])
    def test_production_overlays_are_valid(
        self, env: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Committed production settings must satisfy the production invariants."""
        monkeypatch.setenv("DRUGSIM_ENVIRONMENT", env)
        settings = build_settings()
        assert not settings.debug
        assert settings.log_format == "json"
