#!/usr/bin/env python3
"""Audit dataset licences. Required CI gate (TDS §3.8).

Exits non-zero on any rule violation. Regenerates the attribution manifest as a
side effect so that it cannot drift from the registry.

Usage:
    python scripts/audit_licenses.py [--registry PATH] [--no-write-manifest]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drugsim_quality.license_audit import (  # noqa: E402
    audit_registry,
    build_attribution_manifest,
    load_registry,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Run the audit and return a process exit code."""
    parser = argparse.ArgumentParser(description="Audit DrugSim dataset licences.")
    parser.add_argument("--registry", type=Path, default=ROOT / "datasets" / "registry.yaml")
    parser.add_argument("--no-write-manifest", action="store_true")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    result = audit_registry(registry)

    print(f"Licence audit — {result.sources_checked} active sources checked\n")

    for warning in result.warnings:
        print(f"  WARN   {warning}")
    for error in result.errors:
        print(f"  ERROR  {error}")

    if not args.no_write_manifest:
        manifest_path = ROOT / "docs" / "legal" / "attribution-manifest.md"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(build_attribution_manifest(registry), encoding="utf-8")
        print(f"\n  manifest written to {manifest_path.relative_to(ROOT)}")

    if result.passed:
        print(f"\nPASS — {len(result.warnings)} warning(s), 0 errors")
        return 0
    print(f"\nFAIL — {len(result.errors)} error(s), {len(result.warnings)} warning(s)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
