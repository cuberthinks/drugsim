"""DrugSim database access.

Mirrors the schema defined in ``database/ddl/`` and applied by
``database/migrations/``. See ``engine.py`` for why this package holds
connection/session management rather than a full ORM model layer in Sprint 2.2 —
the schema's heavy use of custom cartridge types, domains, partitioning and
triggers cannot be safely hand-mapped without a live database to verify against.

Modules:
    engine: Engine and session factory, RDKit cartridge verification.
    audit: The one place session-local audit attribution is set, safely.
    registry_sync: Sync datasets/registry.yaml into the data_source table
        (Sprint 2.3), split into a pure planning phase and a thin I/O phase.
    snapshots: Record a completed Z1 download as an ingestion_snapshot row
        (Sprint 2.4), same pure/thin-I/O split.
"""

from __future__ import annotations

from drugsim_db.audit import audit_context
from drugsim_db.engine import get_engine, get_sessionmaker, session_scope, verify_rdkit_cartridge
from drugsim_db.registry_sync import (
    ExistingSource,
    LicenseChange,
    SourceSyncPlan,
    apply_source_sync,
    complete_ingestion_run,
    plan_source_sync,
    start_ingestion_run,
)
from drugsim_db.snapshots import build_snapshot_record, record_ingestion_snapshot

__all__ = [
    "ExistingSource",
    "LicenseChange",
    "SourceSyncPlan",
    "apply_source_sync",
    "audit_context",
    "build_snapshot_record",
    "complete_ingestion_run",
    "get_engine",
    "get_sessionmaker",
    "plan_source_sync",
    "record_ingestion_snapshot",
    "session_scope",
    "start_ingestion_run",
    "verify_rdkit_cartridge",
]
