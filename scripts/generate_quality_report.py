#!/usr/bin/env python3
"""Generate the Phase 2 data-quality report.

Runs the real ETL pipeline (parse -> standardise -> identity -> descriptors ->
drug-likeness) over the golden reference compound set, exercising exactly the
"invalid molecules must be rejected or quarantined" rule: a StructureError on
any one record is caught and recorded as a quarantine, never allowed to abort
the batch or to be silently dropped. It also runs the licence audit against
the live dataset registry and duplicate detection over the batch's InChIKeys.

Deliberately does NOT fabricate a measurement dataset to exercise
aggregation.py/unit_verification.py: Phase 2 (in this environment, with no
Docker/Postgres available) ingested chemistry reference data only, not a real
bioactivity source. Manufacturing synthetic measurements to make this report
look more complete than the actual ingested data would misrepresent what
Phase 2 actually did (P12: honest failure over confident error) -- that gap
is reported explicitly instead, in the "Not exercised this run" section.

Usage:
    python scripts/generate_quality_report.py
"""

from __future__ import annotations

import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import csv  # noqa: E402

from drugsim_chem import (  # noqa: E402
    DESCRIPTOR_SPEC_VERSION,
    STANDARDIZATION_PIPELINE_VERSION,
    process_structure,
)
from drugsim_core.errors import StructureError  # noqa: E402
from drugsim_core.version import get_rdkit_version, get_toolchain_id  # noqa: E402
from drugsim_quality.dedup import find_compound_duplicates  # noqa: E402
from drugsim_quality.license_audit import audit_registry, load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COMPOUNDS_CSV = ROOT / "datasets" / "golden" / "compounds.csv"
REGISTRY_YAML = ROOT / "datasets" / "registry.yaml"
OUTPUT_MD = ROOT / "docs" / "phase2" / "data_quality_report.md"


def _mean(values: list[float]) -> float:
    return statistics.mean(values) if values else 0.0


def main() -> int:
    """Run the pipeline over the reference set and write the report."""
    with COMPOUNDS_CSV.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    processed = []
    quarantined: list[tuple[str, str, str]] = []
    for row in rows:
        try:
            result = process_structure(row["smiles"])
        except StructureError as exc:
            quarantined.append((row["name"], row["smiles"], str(exc)))
            continue
        processed.append((row["name"], result))

    duplicates = find_compound_duplicates(
        [(name, result.identity.inchikey_full) for name, result in processed]
    )

    mixtures = [r for _, r in processed if r.is_mixture]
    whole_salts = [
        r for _, r in processed if "retained_whole_salt_no_organic_parent" in r.standardization.flags
    ]
    salt_stripped = [r for _, r in processed if "salt_stripped" in r.standardization.flags]
    charge_neutralised = [r for _, r in processed if "charge_neutralised" in r.standardization.flags]
    with_descriptors = [r for _, r in processed if r.descriptors is not None]

    mw_values = [r.descriptors.mw_g_mol for r in with_descriptors]
    logp_values = [r.descriptors.logp_crippen for r in with_descriptors]
    lipinski_pass = [r for r in with_descriptors if r.drug_likeness.lipinski_pass]
    pains_flagged = [r for r in with_descriptors if r.drug_likeness.pains_alerts > 0]
    brenk_flagged = [r for r in with_descriptors if r.drug_likeness.brenk_alerts > 0]

    try:
        registry = load_registry(REGISTRY_YAML)
        license_result = audit_registry(registry)
    except (FileNotFoundError, ValueError) as exc:
        license_result = None
        license_error = str(exc)
    else:
        license_error = None

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    toolchain_id = get_toolchain_id(STANDARDIZATION_PIPELINE_VERSION)

    lines = [
        "# DrugSim Phase 2 — Data Quality Report",
        "",
        f"Generated: {generated_at}",
        f"Toolchain: `{toolchain_id}`",
        f"RDKit: {get_rdkit_version()} · Standardisation pipeline: "
        f"{STANDARDIZATION_PIPELINE_VERSION} · Descriptor spec: {DESCRIPTOR_SPEC_VERSION}",
        "",
        "## Dataset processed",
        "",
        f"- Reference compound set: `datasets/golden/compounds.csv` "
        f"({len(rows)} records, hand-curated for edge-case coverage — not an "
        "external licensed source)",
        "- No large-scale external source (ChEMBL/BindingDB/PDB bulk) was "
        "ingested end-to-end in this environment (no Docker/Postgres "
        "available to load into); Sprint 2.4's downloader was verified "
        "against one real file (RCSB `1CRN.pdb`) over a live network "
        "connection, but that is a mechanism check, not a dataset ingest.",
        "",
        "## ETL outcome",
        "",
        f"- Records attempted: {len(rows)}",
        f"- Processed successfully: {len(processed)}",
        f"- Quarantined (StructureError): {len(quarantined)}",
    ]

    if quarantined:
        lines.append("")
        lines.append("| name | smiles | error |")
        lines.append("|---|---|---|")
        for name, smiles, err in quarantined:
            lines.append(f"| {name} | `{smiles}` | {err} |")

    lines += [
        "",
        "## Standardisation",
        "",
        f"- Flagged mixtures (no descriptors computed): {len(mixtures)}",
        f"- Whole-salt structures (no organic parent): {len(whole_salts)}",
        f"- Salt-stripped to a single parent: {len(salt_stripped)}",
        f"- Charge-neutralised: {len(charge_neutralised)}",
        "",
        "## Duplicate detection",
        "",
        f"- Duplicate InChIKey groups found: {len(duplicates)}"
        + (" (expected 0 — the reference set is curated to be distinct)" if not duplicates else ""),
    ]
    for group in duplicates:
        lines.append(f"  - `{group.key}`: {', '.join(group.record_ids)}")

    lines += [
        "",
        "## Descriptors & drug-likeness "
        f"(n={len(with_descriptors)}, mixtures excluded)",
        "",
        f"- MW (g/mol): mean {_mean(mw_values):.1f}, "
        f"min {min(mw_values, default=0):.1f}, max {max(mw_values, default=0):.1f}",
        f"- LogP (Crippen): mean {_mean(logp_values):.2f}, "
        f"min {min(logp_values, default=0):.2f}, max {max(logp_values, default=0):.2f}",
        f"- Lipinski pass: {len(lipinski_pass)}/{len(with_descriptors)}",
        f"- PAINS-flagged: {len(pains_flagged)}/{len(with_descriptors)}",
        f"- Brenk-flagged: {len(brenk_flagged)}/{len(with_descriptors)}",
        "",
        "## Licence audit",
        "",
    ]
    if license_result is None:
        lines.append(f"- **Could not run**: {license_error}")
    else:
        lines.append(f"- Sources checked: {license_result.sources_checked}")
        lines.append(f"- Result: {'PASS' if license_result.passed else 'FAIL'}")
        lines.append(f"- Errors: {len(license_result.errors)}, Warnings: {len(license_result.warnings)}")
        for err in license_result.errors:
            lines.append(f"  - ERROR: {err}")
        for warn in license_result.warnings:
            lines.append(f"  - WARN: {warn}")

    lines += [
        "",
        "## Not exercised this run",
        "",
        "- **Measurement aggregation / discordance flags** "
        "(`drugsim_quality.aggregation`) — implemented and unit-tested "
        "(`tests/unit/test_aggregation.py`), but no real bioactivity "
        "measurement dataset was ingested this phase to run it against.",
        "- **Empirical unit verification** (`drugsim_quality.unit_verification`) "
        "— same reason: no measurement dataset to verify units on.",
        "- **Bulk load into PostgreSQL** — `src/drugsim_db/bulk_load.py` is "
        "implemented and unit-tested against real pipeline output; the "
        "insert path is exercised in `tests/constraints/test_bulk_load_integration.py`, "
        "which requires Docker and did not run in this environment.",
        "",
    ]

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
