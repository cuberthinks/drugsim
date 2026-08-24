"""Alembic environment.

Two decisions here diverge from the Alembic default and are worth stating:

**No declarative model metadata, no autogenerate.** ``target_metadata`` is left
``None``. Autogenerate is poor at exactly the things this schema depends on:
custom cartridge types (``mol``, ``bfp``), domains, LIST partitioning, and
hand-written triggers. Every migration in this project is written by hand, in
raw SQL, for full control over these — see ``database/ddl/README.md``.

**The connection URL comes from application settings, not from ``alembic.ini``.**
A database password does not belong in a committed file (TDS §7.6); it is
resolved through the same layered configuration and secret handling as the rest
of the application.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from drugsim_core.config import get_settings  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None  # see module docstring


def _database_url() -> str:
    """Resolve the database URL, preferring an explicit override.

    An explicit ``sqlalchemy.url`` already set on the Alembic config (e.g.
    by a test fixture pointing migrations at an ephemeral database) takes
    precedence over application settings. Application settings are the
    correct source for every real invocation -- a database password does
    not belong in a committed file (TDS §7.6) -- but a caller that has
    already resolved a specific URL itself must not be silently
    overridden. Without this, tests/constraints/conftest.py's
    ``cfg.set_main_option("sqlalchemy.url", url)`` had no effect at all:
    migrations always ran against the default localhost settings instead
    of the testcontainers-managed database, so the entire constraint
    suite failed at fixture setup rather than exercising anything.

    Returns:
        A SQLAlchemy connection URL, including the password.
    """
    explicit = config.get_main_option("sqlalchemy.url")
    if explicit:
        return explicit
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live database connection."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live database connection."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
