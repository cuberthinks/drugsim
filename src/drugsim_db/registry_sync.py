"""Sync ``datasets/registry.yaml`` into the ``data_source`` table.

Split deliberately into a pure planning phase and a thin I/O phase.
:func:`plan_source_sync` takes the registry and a plain description of what is
already in the database and returns a plan — no database connection involved.
:func:`apply_source_sync` executes that plan.

This split exists so the part of this module most likely to contain a bug — the
decision logic — can be exercised by ordinary unit tests with no database at all,
while the part that actually touches the database (small, and largely a direct
translation of the plan into SQL) is exercised by an integration test against a
real instance (``tests/constraints/test_registry_sync.py``, unverified in this
environment — see Sprint 2.3 notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from drugsim_core.errors import LicenseViolationError
from drugsim_core.ids import generate_ulid
from drugsim_quality.license_audit import TIER_BY_SPDX, LicenseTier

__all__ = [
    "ExistingSource",
    "LicenseChange",
    "SourceSyncPlan",
    "apply_source_sync",
    "complete_ingestion_run",
    "plan_source_sync",
    "start_ingestion_run",
]

#: Fields that, if changed, are applied automatically — cosmetic or operational,
#: never a commercial-use decision.
_SAFE_TO_AUTO_UPDATE = frozenset(
    {"name", "homepage", "role", "attribution_text", "cadence_days", "notes", "verification_status"}
)


@dataclass(frozen=True)
class ExistingSource:
    """The subset of a current ``data_source`` row this module cares about.

    A plain dataclass rather than an ORM row, specifically so
    :func:`plan_source_sync` can be called with hand-built test fixtures and
    never needs a database to run.
    """

    source_id: str
    license_spdx: str
    license_tier: str
    is_commercial_ok: bool
    has_sharealike: bool
    name: str = ""
    homepage: str = ""
    role: str = ""
    attribution_text: str = ""
    cadence_days: int | None = None
    notes: str | None = None
    verification_status: str = "unverified"


@dataclass(frozen=True)
class LicenseChange:
    """A registry entry whose licence differs from what is currently stored.

    Rule LC-04 (Phase 1 Step 8 §10.3): an upstream relicensing is a material
    event requiring human review, not something to silently apply. Every field
    that changed is recorded, not just SPDX, because a tier or commercial-use
    flag can change even when SPDX text is copied forward incorrectly.
    """

    source_id: str
    old_spdx: str
    new_spdx: str
    old_tier: str
    new_tier: str


@dataclass
class SourceSyncPlan:
    """The result of comparing the registry against current database state.

    Attributes:
        to_insert: New source rows to create, as ready-to-bind parameter dicts.
        to_update: ``(source_id, changed_fields)`` pairs for safe, automatic
            field updates.
        license_changes: Detected licence changes. Non-empty blocks
            :func:`apply_source_sync` unless explicitly acknowledged.
        unchanged: Source ids present in both and requiring no action.
    """

    to_insert: list[dict[str, Any]] = field(default_factory=list)
    to_update: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    license_changes: list[LicenseChange] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def is_safe_to_apply(self) -> bool:
        """Whether this plan can be applied without explicit override."""
        return not self.license_changes


#: Tier restrictiveness, least to most. Used to collapse a split-licensed
#: source to a single effective tier.
_TIER_SEVERITY: dict[str, int] = {
    LicenseTier.GREEN.value: 0,
    LicenseTier.AMBER.value: 1,
    LicenseTier.RED.value: 2,
    LicenseTier.BLACK.value: 3,
}


def _effective_tier(entry: dict[str, Any], licence: dict[str, Any]) -> str:
    """Collapse a split-licensed source to the single tier the database stores.

    ``license_tier_t`` is ``ENUM('green','amber','red','black')`` on purpose:
    ADR-007 makes licence tier a physical partition so that "can we ship this?"
    is answerable by a SQL predicate alone. Adding a fifth ``mixed`` member
    would destroy that property -- a ``mixed`` row answers the question with
    "it depends", which is exactly what the partition exists to prevent. So a
    ``mixed`` registry entry is resolved here instead, and the fact that it was
    split is preserved separately in ``is_split_licensed``.

    Resolution rules, both conservative:

    - ``split_licensing`` present: every listed portion is ingested, so the
      effective tier is the most restrictive portion. BindingDB (CC-BY-3.0
      curated + CC-BY-SA-3.0 ChEMBL-derived) resolves to ``red``, carrying the
      ShareAlike obligation of its strictest part.
    - Otherwise ``default_tier``/``default_spdx``: entries under ``exclusions``
      are gated out before ingestion rather than ingested, so they do not drag
      the whole source down. TDC resolves to its ``amber`` default even though
      it lists a ``black`` FreeSolv exclusion -- and that only holds while the
      exclusion really is hard-gated in code, which the registry asserts.

    Args:
        entry: One item from ``registry["sources"]``.
        licence: That entry's ``license`` block.

    Returns:
        A tier string valid for the ``license_tier_t`` enum.

    Raises:
        LicenseViolationError: If a ``mixed`` entry declares neither
            ``split_licensing`` nor a default tier, leaving nothing to resolve.
    """
    declared = licence.get("tier")
    if declared != LicenseTier.MIXED.value:
        return str(declared)

    portions = licence.get("split_licensing") or []
    tiers = [str(p["tier"]) for p in portions if p.get("tier")]
    if tiers:
        return max(tiers, key=lambda t: _TIER_SEVERITY.get(t, _TIER_SEVERITY[LicenseTier.BLACK.value]))

    default_tier = licence.get("default_tier")
    if default_tier is None and licence.get("default_spdx"):
        mapped = TIER_BY_SPDX.get(str(licence["default_spdx"]))
        default_tier = mapped.value if mapped else None
    if default_tier is not None:
        return str(default_tier)

    msg = (
        f"source {entry.get('source_id')!r} declares tier 'mixed' but provides "
        "neither split_licensing portions nor a default_tier/default_spdx, so "
        "no effective tier can be resolved"
    )
    raise LicenseViolationError(msg, source_id=entry.get("source_id"))


def _commercial_ok(licence: dict[str, Any], effective_tier: str) -> bool:
    """Resolve ``commercial_ok`` to a strict boolean.

    The registry uses the string ``"partial"`` for sources that are only
    conditionally usable commercially (TDC). ``bool("partial")`` is ``True``,
    which would record a conditional source as unconditionally shippable --
    an overclaim in exactly the direction that matters. Anything that is not
    literally boolean ``True`` resolves to ``False`` here.
    """
    raw = licence.get("commercial_ok", effective_tier != LicenseTier.BLACK.value)
    return raw is True


def _extract_source_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract the ``data_source`` row fields from one registry entry.

    Args:
        entry: One item from ``registry["sources"]``.

    Returns:
        A flat dict matching the ``data_source`` column names.

    Raises:
        LicenseViolationError: If the entry's licence tier is internally
            inconsistent — this is a second, independent check alongside the
            standalone licence audit (``drugsim_quality.license_audit``),
            because this module is a second call site that could otherwise
            insert a bad row even after the audit script has passed.
    """
    licence = entry.get("license") or {}
    spdx = licence.get("spdx")
    tier_str = licence.get("tier")

    if spdx is None or tier_str is None:
        msg = f"source {entry.get('source_id')!r} has no license.spdx or license.tier"
        raise LicenseViolationError(msg, source_id=entry.get("source_id"))

    if spdx != "MIXED":
        expected = TIER_BY_SPDX.get(spdx)
        if expected is not None and expected.value != tier_str:
            msg = (
                f"source {entry.get('source_id')!r}: registry declares tier "
                f"{tier_str!r} but SPDX {spdx!r} maps to {expected.value!r}"
            )
            raise LicenseViolationError(msg, source_id=entry.get("source_id"))

    effective_tier = _effective_tier(entry, licence)

    # "partial" is a real registry value for sharealike (BindingDB): part of the
    # source carries it, so the stored row must say yes, not be coerced by
    # truthiness that happens to land correctly.
    raw_sharealike = licence.get("sharealike", effective_tier == LicenseTier.RED.value)
    has_sharealike = raw_sharealike is True or raw_sharealike == "partial"

    return {
        "source_id": entry["source_id"],
        "name": entry.get("name", entry["source_id"]),
        "homepage": entry.get("homepage", ""),
        "role": entry.get("role", ""),
        "license_spdx": spdx,
        "license_tier": effective_tier,
        "is_commercial_ok": _commercial_ok(licence, effective_tier),
        "has_sharealike": has_sharealike,
        "attribution_text": licence.get("attribution", ""),
        "cadence_days": (entry.get("cadence") or {}).get("expected_days"),
        "is_split_licensed": spdx == "MIXED",
        "verification_status": (entry.get("verification") or {}).get("status", "unverified"),
        "verification_date": (entry.get("verification") or {}).get("date"),
        "notes": entry.get("notes"),
    }


def plan_source_sync(
    registry: dict[str, Any],
    existing: dict[str, ExistingSource],
) -> SourceSyncPlan:
    """Compute what would change if the registry were synced to the database.

    Pure function: no I/O, no database. ``existing`` describes current state as
    plain data, which is what makes this testable without Docker.

    Args:
        registry: Parsed ``registry.yaml`` (see
            ``drugsim_quality.license_audit.load_registry``).
        existing: Current ``data_source`` rows, keyed by ``source_id``.

    Returns:
        The computed plan.
    """
    plan = SourceSyncPlan()

    for entry in registry.get("sources") or []:
        fields = _extract_source_fields(entry)
        source_id = fields["source_id"]
        current = existing.get(source_id)

        if current is None:
            plan.to_insert.append(fields)
            continue

        if fields["license_spdx"] != current.license_spdx or fields["license_tier"] != current.license_tier:
            plan.license_changes.append(
                LicenseChange(
                    source_id=source_id,
                    old_spdx=current.license_spdx,
                    new_spdx=fields["license_spdx"],
                    old_tier=current.license_tier,
                    new_tier=fields["license_tier"],
                )
            )
            continue

        # Compare against CURRENT values, not merely presence in `fields` — every
        # registry entry has a homepage/name/etc., so checking presence alone
        # would report every field as "changed" on every sync, even when nothing
        # actually differs. (Caught by test_identical_source_is_unchanged.)
        changed = {
            k: fields[k]
            for k in _SAFE_TO_AUTO_UPDATE
            if k in fields and fields[k] != getattr(current, k, object())
        }
        if changed:
            plan.to_update.append((source_id, changed))
        else:
            plan.unchanged.append(source_id)

    return plan


def apply_source_sync(
    session: Session,
    plan: SourceSyncPlan,
    *,
    acknowledge_license_changes: bool = False,
) -> None:
    """Apply a previously computed plan to the database.

    Args:
        session: An active session. Must be used within an
            ``audit_context`` block — every write here goes through the audit
            trigger on ``data_source``.
        plan: The plan from :func:`plan_source_sync`.
        acknowledge_license_changes: Must be explicitly ``True`` to apply a plan
            containing licence changes. The default refusal is the point: rule
            LC-04 requires human review of a relicensing event, and a script
            that silently applied it would defeat that.

    Raises:
        LicenseViolationError: If the plan contains unacknowledged licence
            changes.
    """
    if plan.license_changes and not acknowledge_license_changes:
        details = "; ".join(
            f"{c.source_id}: {c.old_spdx} ({c.old_tier}) -> {c.new_spdx} ({c.new_tier})"
            for c in plan.license_changes
        )
        msg = (
            f"{len(plan.license_changes)} licence change(s) require human review "
            f"before applying (rule LC-04): {details}"
        )
        raise LicenseViolationError(msg, changes=details)

    for fields in plan.to_insert:
        columns = ", ".join(fields)
        placeholders = ", ".join(f":{k}" for k in fields)
        session.execute(
            text(f"INSERT INTO data_source ({columns}) VALUES ({placeholders})"),  # noqa: S608
            fields,
        )

    for source_id, changed_fields in plan.to_update:
        set_clause = ", ".join(f"{k} = :{k}" for k in changed_fields)
        session.execute(
            text(f"UPDATE data_source SET {set_clause} WHERE source_id = :source_id"),  # noqa: S608
            {**changed_fields, "source_id": source_id},
        )


def start_ingestion_run(
    session: Session,
    *,
    snapshot_id: str,
    parser_version: str,
    import_version: str,
    started_by: str,
) -> str:
    """Record the start of an ingestion run and return its id.

    Args:
        session: An active session, used within an ``audit_context`` block.
        snapshot_id: The Z1 snapshot being processed.
        parser_version: Git SHA of the parser code.
        import_version: Git SHA of the import code.
        started_by: A ``system_user.user_uid``.

    Returns:
        The new run's ULID.
    """
    run_uid = generate_ulid()
    session.execute(
        text(
            "INSERT INTO ingestion_run (run_uid, snapshot_id, parser_version, "
            "import_version, started_by) VALUES (:uid, :snap, :pv, :iv, :by)"
        ),
        {"uid": run_uid, "snap": snapshot_id, "pv": parser_version, "iv": import_version, "by": started_by},
    )
    return run_uid


def complete_ingestion_run(
    session: Session,
    run_uid: str,
    *,
    validation_status: str,
    gate_results: dict[str, Any],
    records_parsed: int,
    records_imported: int,
    records_quarantined: int,
    error_summary: str | None = None,
) -> None:
    """Record the outcome of an ingestion run.

    Args:
        session: An active session, used within an ``audit_context`` block.
        run_uid: The run to complete, from :func:`start_ingestion_run`.
        validation_status: One of the ``validation_status_t`` enum values.
        gate_results: Per-gate outcome, keyed by gate id (e.g. ``"G4"``).
        records_parsed: Count of records the parser produced.
        records_imported: Count actually written to the curated layer.
        records_quarantined: Count rejected by a validation gate.
        error_summary: Human-readable summary if the run failed.
    """
    session.execute(
        text(
            "UPDATE ingestion_run SET validation_status = :status, "
            "gate_results = :gates, records_parsed = :parsed, "
            "records_imported = :imported, records_quarantined = :quarantined, "
            "error_summary = :error, completed_at = :completed_at "
            "WHERE run_uid = :uid"
        ),
        {
            "uid": run_uid,
            "status": validation_status,
            "gates": gate_results,
            "parsed": records_parsed,
            "imported": records_imported,
            "quarantined": records_quarantined,
            "error": error_summary,
            "completed_at": datetime.now(timezone.utc),
        },
    )
