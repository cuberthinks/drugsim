"""DrugSim command-line interface.

Thin operational surface over the platform. Deliberately minimal: the CLI is for
operators running pipeline stages and inspecting state, not a second API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from drugsim_core.config import build_settings
from drugsim_core.logging import configure_logging, get_logger
from drugsim_core.version import get_rdkit_version, get_toolchain_id, get_version

app = typer.Typer(
    name="drugsim",
    help="DrugSim data platform operations.",
    no_args_is_help=True,
    add_completion=False,
)

db_app = typer.Typer(help="Database schema and migration operations.", no_args_is_help=True)
app.add_typer(db_app, name="db")

ingest_app = typer.Typer(help="Raw data acquisition (Z1 landing).", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")


@app.command()
def version() -> None:
    """Print version and toolchain identification."""
    payload = {
        "version": get_version(),
        "rdkit_version": get_rdkit_version(),
        "toolchain_id": get_toolchain_id(),
    }
    typer.echo(json.dumps(payload, indent=2))


@app.command()
def config(show_secrets: bool = typer.Option(False, help="Reveal secret values.")) -> None:
    """Print the resolved configuration.

    Secrets are masked unless explicitly requested, so that pasting output into a
    ticket does not disclose credentials.
    """
    settings = build_settings()
    data = settings.model_dump(mode="json")
    if not show_secrets:
        for key in data:
            if "password" in key or "secret" in key or "access_key" in key:
                data[key] = "***"
    typer.echo(json.dumps(data, indent=2, default=str))


@app.command("check-config")
def check_config() -> None:
    """Validate configuration and assert no secrets are committed.

    Intended as a startup and CI check.
    """
    from drugsim_core.config import Settings

    settings = build_settings()
    Settings.assert_no_secrets_in_yaml(settings.config_dir)
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    get_logger(__name__).info(
        "configuration valid",
        environment=settings.environment.value,
        toolchain_id=get_toolchain_id(),
    )
    typer.echo("OK")


@app.command("audit-licenses")
def audit_licenses(
    registry: Path = typer.Option(None, help="Path to registry.yaml."),
) -> None:
    """Audit dataset licences against rules LC-01 … LC-06."""
    from drugsim_quality.license_audit import audit_registry, load_registry

    settings = build_settings()
    path = registry or settings.registry_path
    result = audit_registry(load_registry(path))

    for warning in result.warnings:
        typer.echo(f"WARN   {warning}")
    for error in result.errors:
        typer.secho(f"ERROR  {error}", fg=typer.colors.RED)

    if not result.passed:
        typer.secho(f"FAIL — {len(result.errors)} error(s)", fg=typer.colors.RED)
        sys.exit(1)
    typer.secho(
        f"PASS — {result.sources_checked} sources, {len(result.warnings)} warning(s)",
        fg=typer.colors.GREEN,
    )


@db_app.command("sync-registry")
def db_sync_registry(
    registry: Path = typer.Option(None, help="Path to registry.yaml."),
    reason: str = typer.Option(..., help="Audit reason for this sync."),
    acknowledge_license_changes: bool = typer.Option(
        False, help="Required to apply a plan containing a detected licence change (rule LC-04)."
    ),
    dry_run: bool = typer.Option(False, help="Compute and print the plan without applying it."),
) -> None:
    """Sync datasets/registry.yaml into the data_source table.

    Runs the licence audit first — a plan is never applied against a registry
    that does not itself pass LC-01…LC-06.
    """
    from drugsim_core.errors import LicenseViolationError
    from drugsim_core.ids import SYSTEM_USER_UID
    from drugsim_db.audit import audit_context
    from drugsim_db.engine import session_scope
    from drugsim_db.registry_sync import ExistingSource, apply_source_sync, plan_source_sync
    from drugsim_quality.license_audit import audit_registry, load_registry
    from sqlalchemy import text

    settings = build_settings()
    path = registry or settings.registry_path
    parsed_registry = load_registry(path)

    audit_result = audit_registry(parsed_registry)
    if not audit_result.passed:
        typer.secho(
            f"Registry fails its own licence audit ({len(audit_result.errors)} error(s)) — "
            "refusing to sync. Run 'drugsim audit-licenses' for detail.",
            fg=typer.colors.RED,
        )
        sys.exit(1)

    with session_scope() as session:
        rows = session.execute(
            text(
                "SELECT source_id, license_spdx, license_tier, is_commercial_ok, "
                "has_sharealike, name, homepage, role, attribution_text, "
                "cadence_days, notes, verification_status FROM data_source"
            )
        ).mappings()
        existing = {row["source_id"]: ExistingSource(**dict(row)) for row in rows}

        plan = plan_source_sync(parsed_registry, existing)

        typer.echo(
            f"Plan: {len(plan.to_insert)} insert(s), {len(plan.to_update)} update(s), "
            f"{len(plan.unchanged)} unchanged, {len(plan.license_changes)} licence change(s)"
        )
        for change in plan.license_changes:
            typer.secho(
                f"  LICENCE CHANGE {change.source_id}: {change.old_spdx} ({change.old_tier}) "
                f"-> {change.new_spdx} ({change.new_tier})",
                fg=typer.colors.YELLOW,
            )

        if dry_run:
            typer.echo("Dry run — nothing applied.")
            return

        try:
            with audit_context(session, user_id=SYSTEM_USER_UID, reason=reason):
                apply_source_sync(
                    session, plan, acknowledge_license_changes=acknowledge_license_changes
                )
        except LicenseViolationError as exc:
            typer.secho(f"BLOCKED: {exc.message}", fg=typer.colors.RED)
            typer.echo("Re-run with --acknowledge-license-changes after human review.")
            sys.exit(1)

    typer.secho("Sync applied.", fg=typer.colors.GREEN)


@db_app.command("upgrade")
def db_upgrade(
    revision: str = typer.Argument("head", help="Target revision, e.g. 'head' or '0007'."),
) -> None:
    """Apply pending migrations up to the given revision (default: head)."""
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(project_root / "alembic.ini"))
    command.upgrade(cfg, revision)
    typer.secho(f"upgraded to {revision}", fg=typer.colors.GREEN)


@db_app.command("current")
def db_current() -> None:
    """Show the current database revision."""
    from alembic import command
    from alembic.config import Config

    project_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(project_root / "alembic.ini"))
    command.current(cfg, verbose=True)


@db_app.command("verify-rdkit")
def db_verify_rdkit() -> None:
    """Assert the RDKit cartridge is installed and print its version.

    Fails fast with a clear message rather than letting the first compound
    insert produce a cryptic error (ADR-003).
    """
    from drugsim_db.engine import get_engine, verify_rdkit_cartridge
    from sqlalchemy.orm import Session

    with Session(get_engine()) as session:
        cartridge_version = verify_rdkit_cartridge(session)
    typer.secho(f"RDKit cartridge OK: {cartridge_version}", fg=typer.colors.GREEN)


@db_app.command("ensure-partitions")
def db_ensure_partitions(
    months_ahead: int = typer.Option(3, help="Months beyond the current one to pre-create."),
) -> None:
    """Create upcoming audit_log partitions ahead of need.

    Intended to run on a schedule (see scripts/ensure_audit_partitions.py, which
    this command wraps) — audit_log ships with only a DEFAULT partition, and
    everything lands there until explicit monthly ranges exist.
    """
    import subprocess  # noqa: S404

    script = Path(__file__).resolve().parents[2] / "scripts" / "ensure_audit_partitions.py"
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), "--months-ahead", str(months_ahead)],
        check=False,
    )
    sys.exit(result.returncode)


@ingest_app.command("download")
def ingest_download(
    source_id: str = typer.Argument(..., help="Registry source id, e.g. 'chembl'."),
    url: str = typer.Option(..., help="URL to download."),
    filename: str = typer.Option(..., help="Filename to store under in the landing zone."),
    expected_sha256: str = typer.Option(None, help="Expected checksum, if known in advance."),
    reason: str = typer.Option(..., help="Audit reason for this ingestion."),
) -> None:
    """Download a file, land it immutably in Z1, and record the snapshot.

    Ties together drugsim_ingest.downloader, .landing, and .snapshot with
    drugsim_db.snapshots — the full path from a URL to a queryable,
    provenance-tracked ingestion_snapshot row.
    """
    import tempfile
    from datetime import datetime, timezone

    from drugsim_core.ids import SYSTEM_USER_UID
    from drugsim_db.audit import audit_context
    from drugsim_db.engine import session_scope
    from drugsim_db.snapshots import build_snapshot_record, record_ingestion_snapshot
    from drugsim_ingest.downloader import download_to_file
    from drugsim_ingest.landing import LandingZone
    from drugsim_ingest.snapshot import build_landing_key
    from drugsim_quality.license_audit import load_registry

    settings = build_settings()
    registry = load_registry(settings.registry_path)
    source = next((s for s in registry["sources"] if s["source_id"] == source_id), None)
    if source is None:
        typer.secho(f"unknown source_id {source_id!r} — not in registry.yaml", fg=typer.colors.RED)
        sys.exit(1)

    license_tier = source["license"].get("tier", "black")
    license_spdx = source["license"].get("spdx", "UNKNOWN")
    source_version = source.get("upstream_version", "unknown")

    with tempfile.TemporaryDirectory() as tmpdir:
        local_path = Path(tmpdir) / filename
        typer.echo(f"Downloading {url} ...")
        result = download_to_file(url, local_path, expected_sha256=expected_sha256)
        typer.echo(f"Downloaded {result.byte_size} bytes, sha256={result.sha256}")

        # snapshot_id is derived from the content digest, so it is only known
        # once the download (and its checksum) has completed.
        from drugsim_ingest.snapshot import build_snapshot_id

        acquired_at = datetime.now(timezone.utc)
        snapshot_id = build_snapshot_id(source_version, acquired_at, result.sha256)
        key = build_landing_key(license_tier, source_id, snapshot_id, filename)

        landing = LandingZone(settings.bucket_landing, endpoint_url=settings.object_storage_endpoint)
        metadata = landing.write_immutable(
            key, local_path.read_bytes(), expected_sha256=result.sha256
        )
        typer.echo(f"Landed at {settings.bucket_landing}/{key}")

    fields = build_snapshot_record(
        source_id=source_id,
        source_version=source_version,
        acquired_at=acquired_at,
        content_sha256=metadata.sha256,
        byte_size=metadata.byte_size,
        landing_uri=f"s3://{settings.bucket_landing}/{key}",
        license_at_time=license_spdx,
    )

    with session_scope() as session:
        with audit_context(session, user_id=SYSTEM_USER_UID, reason=reason):
            record_ingestion_snapshot(session, fields)

    typer.secho(f"Recorded snapshot {fields['snapshot_id']}", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
