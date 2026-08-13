"""Fixtures for constraint tests: a real PostgreSQL 16 + RDKit cartridge instance.

**Requires Docker.** These tests cannot run against SQLite or a mock — the schema
pushes integrity into cartridge types (``mol``, ``bfp``), domains, LIST
partitioning, and ``CONSTRAINT TRIGGER``-equivalent PL/pgSQL triggers, none of
which those alternatives can exercise (TDS §9.3).

The container is built from ``deployment/docker/Dockerfile.postgres-rdkit`` —
the same image used in production — rather than a stock ``postgres:16``, so a
missing cartridge is caught here rather than in production.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.core.image import DockerImage
from testcontainers.postgres import PostgresContainer

from drugsim_core.ids import SYSTEM_USER_UID, generate_ulid

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def postgres_rdkit_image() -> Iterator[str]:
    """Build the postgres-rdkit image once per test session.

    Building from the Dockerfile (rather than assuming a pre-built tag exists)
    means ``make test-all`` is self-contained for a developer who has not run a
    separate image-build step, and means a Dockerfile regression is caught here
    rather than only in the CI ``docker`` job.

    Yields:
        The built image tag.
    """
    with DockerImage(
        path=str(PROJECT_ROOT),
        dockerfile_path="deployment/docker/Dockerfile.postgres-rdkit",
        tag="drugsim/postgres-rdkit:test",
    ) as image:
        yield str(image)


@pytest.fixture(scope="session")
def postgres_container(postgres_rdkit_image: str) -> Iterator[PostgresContainer]:
    """Start a PostgreSQL + RDKit container for the test session.

    Args:
        postgres_rdkit_image: The built image tag.

    Yields:
        The running container.
    """
    with PostgresContainer(
        image=postgres_rdkit_image,
        username="drugsim",
        password="test_password_not_for_production",
        dbname="drugsim_test",
    ) as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres_container: PostgresContainer) -> Engine:
    """Return an engine connected to the test container, with migrations applied.

    Migrations are applied via Alembic's public API rather than by re-executing
    ``database/ddl/*.sql`` directly — this is what actually verifies the migration
    history, not just the schema's final shape, which is the point of a
    constraint test suite living alongside a forward-only migration policy.

    Args:
        postgres_container: The running container.

    Returns:
        A connected, migrated engine.
    """
    from alembic import command
    from alembic.config import Config

    url = postgres_container.get_connection_url().replace(
        "postgresql+psycopg2", "postgresql+psycopg"
    )
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    return create_engine(url, pool_pre_ping=True)


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Provide a session wrapped in a transaction that rolls back after each test.

    Rollback-per-test keeps the ~10,000-row golden-set-adjacent fixtures and the
    35-table schema cheap to test against repeatedly without needing to truncate
    or re-migrate between tests.

    Args:
        engine: The migrated engine.

    Yields:
        A session bound to a savepoint-nested transaction.
    """
    connection = engine.connect()
    transaction = connection.begin()
    factory = sessionmaker(bind=connection)
    db_session = factory()
    try:
        yield db_session
    finally:
        db_session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def curator_user_id(session: Session) -> str:
    """Create a non-bootstrap system_user for tests that need a 'real' actor.

    The bootstrap account (SYSTEM_USER_UID) exists for migration-time genesis
    writes; most tests should attribute changes to an ordinary curator instead,
    so a test asserting "changed_by is recorded correctly" is not accidentally
    trivially true because everything defaults to the one bootstrap row.

    Args:
        session: An active session.

    Returns:
        The new user's ULID.
    """
    from drugsim_db.audit import audit_context

    user_id = generate_ulid()
    with audit_context(session, user_id=SYSTEM_USER_UID, reason="test fixture setup"):
        session.execute(
            text(
                "INSERT INTO system_user (user_uid, username, full_name, email, role) "
                "VALUES (:uid, :username, 'Test Curator', 'curator@test.local', 'curator')"
            ),
            {"uid": user_id, "username": f"curator_{user_id[:8]}"},
        )
    session.flush()
    return user_id
