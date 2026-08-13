"""Database engine and session management.

A thin layer over SQLAlchemy Core. There is no declarative ORM model layer in
Sprint 2.2: the schema makes heavy use of the RDKit cartridge's custom types
(``mol``, ``bfp``), domains, LIST partitioning and triggers, none of which a
hand-written ORM mapping can be tested against without a live cartridge-enabled
Postgres — unavailable in the environment this sprint was authored in. Building
~35 fully-typed ORM classes with no way to verify them against a real database
risks a large surface of plausible-looking, unverified code. ORM models are
added incrementally, per domain, as later sprints actually query each one and
can verify the mapping against `tests/constraints`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from drugsim_core.config import Settings, get_settings

__all__ = ["get_engine", "get_sessionmaker", "session_scope", "verify_rdkit_cartridge"]


@lru_cache(maxsize=1)
def get_engine(settings: Settings | None = None) -> Engine:
    """Return the process-wide SQLAlchemy engine.

    Cached because engines own a connection pool; creating one per call would
    exhaust database connections under load.

    Args:
        settings: Settings to build the engine from. Defaults to the process
            settings singleton. Only override in tests, where the cache should
            also be cleared via ``get_engine.cache_clear()``.

    Returns:
        A configured, pooled engine.
    """
    resolved = settings if settings is not None else get_settings()
    return create_engine(
        resolved.database_url,
        pool_size=resolved.database_pool_size,
        pool_pre_ping=True,
        connect_args={"options": f"-c statement_timeout={resolved.database_statement_timeout_ms}"},
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide session factory.

    Returns:
        A configured ``sessionmaker``.
    """
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session, committing on success and rolling back on error.

    Yields:
        An active session.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def verify_rdkit_cartridge(session: Session) -> str:
    """Assert the RDKit cartridge is installed and return its version.

    Intended as a startup check and a CLI command
    (``drugsim db verify-rdkit``) — the platform is unusable without the
    cartridge (ADR-003), and failing fast with a clear message beats a cryptic
    error the first time a compound is inserted.

    Args:
        session: An active database session.

    Returns:
        The installed RDKit cartridge version string.

    Raises:
        RuntimeError: If the ``rdkit`` extension is not installed.
    """
    row = session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'rdkit'")
    ).first()
    if row is None:
        msg = (
            "RDKit cartridge is not installed in this database. DrugSim cannot "
            "function without it (ADR-003) — substructure and similarity search "
            "depend on the mol/bfp types and their GiST opclasses. Check that "
            "the postgres-rdkit image is in use, not stock postgres:16."
        )
        raise RuntimeError(msg)
    return str(row[0])
