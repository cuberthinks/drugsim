"""DrugSim data quality: licence audit, unit determination, deduplication.

Home of the empirical unit-determination protocol (Phase 1 Step 8 §5), which exists
because Therapeutics Data Commons does not document units for most ADME/Tox
endpoints. Unit correctness is therefore asserted from data — range, distribution
shape, and reference compounds — never from documentation.

Modules:
    license_audit: Rules LC-01…LC-06 against datasets/registry.yaml (Sprint 2.1).
    unit_verification: Gate G4 — range, distribution shape, and reference-compound
        checks (Sprint 2.5).
    dedup: Intra- and cross-source duplicate grouping, never deletion (Sprint 2.5).
    aggregation: Geometric-mean/median/majority-vote aggregation with discordance
        flags — a recorded decision, never a silent average (measurement_aggregate).

Registry-to-database sync (also pure-planning-plus-thin-I/O in the same style)
lives in ``drugsim_db.registry_sync`` instead, since it owns the DB write path.
"""

from __future__ import annotations

from drugsim_quality.aggregation import AggregationResult, aggregate_binary, aggregate_continuous
from drugsim_quality.dedup import DuplicateGroup, find_compound_duplicates, find_measurement_duplicates
from drugsim_quality.license_audit import (
    TIER_BY_SPDX,
    AuditResult,
    LicenseTier,
    audit_registry,
    build_attribution_manifest,
    load_registry,
)
from drugsim_quality.unit_verification import (
    ReferenceCompoundCheck,
    UnitVerificationResult,
    verify_range,
    verify_reference_compounds,
    verify_skewness_consistent_with_log_scale,
)

__all__ = [
    "TIER_BY_SPDX",
    "AggregationResult",
    "AuditResult",
    "DuplicateGroup",
    "LicenseTier",
    "ReferenceCompoundCheck",
    "UnitVerificationResult",
    "aggregate_binary",
    "aggregate_continuous",
    "audit_registry",
    "build_attribution_manifest",
    "find_compound_duplicates",
    "find_measurement_duplicates",
    "load_registry",
    "verify_range",
    "verify_reference_compounds",
    "verify_skewness_consistent_with_log_scale",
]
