#!/usr/bin/env python3
"""Verify every registered model artifact before a deployment proceeds.

Phase 8 model change control / CI-CD gate: this is the same integrity
verification that runs lazily inside the running service on first request
(``drugsim_predict.model_registry.load_model_bundle``), but run explicitly
and eagerly as a discrete pre-deploy step so that a missing or
checksum-mismatched artifact fails the *deployment pipeline*, rather than
being discovered only when the first real request (or health check) hits a
freshly-started, broken instance.

Phase 10 fix: this originally checked only the single, implicit default
model (hERG) via a no-argument ``load_model_bundle()`` call -- a pre-Phase-9
artifact that meant a CI/CD run of this gate never actually verified the
CYP3A4 artifact at all, silently. It now enumerates every endpoint the
registry knows about (``list_registered_endpoints()``) and checksum-verifies
each one; a deployment with N registered endpoints gets N verified
artifacts, not one.

Exits non-zero and prints a clear reason on any failure. Never proceeds
past a checksum mismatch or missing artifact -- there is no "warn and
continue" here, matching every other integrity check in this codebase. One
endpoint failing fails the whole gate: a partially-verified deployment is
not a passing one.

Usage:
    python scripts/verify_model_integrity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from drugsim_core.errors import IntegrityError, UnknownEndpointError  # noqa: E402
from drugsim_predict.model_registry import list_registered_endpoints, load_model_bundle  # noqa: E402


def main() -> int:
    try:
        endpoints = list_registered_endpoints()
    except FileNotFoundError as exc:
        print(f"MODEL REGISTRY DIRECTORY NOT FOUND: {exc}", file=sys.stderr)
        return 1

    if not endpoints:
        print("MODEL INTEGRITY CHECK FAILED: no endpoints are registered.", file=sys.stderr)
        return 1

    overall_ok = True
    for summary in endpoints:
        print(f"--- {summary.model_id} ---")
        try:
            bundle = load_model_bundle(model_id=summary.model_id)
        except (IntegrityError, UnknownEndpointError) as exc:
            print(f"MODEL INTEGRITY CHECK FAILED for {summary.model_id!r}: {exc}", file=sys.stderr)
            overall_ok = False
            continue
        except FileNotFoundError as exc:
            print(f"MODEL REGISTRY FILE NOT FOUND for {summary.model_id!r}: {exc}", file=sys.stderr)
            overall_ok = False
            continue

        print("  Model integrity check passed.")
        print(f"  model_id:            {bundle.model_id}")
        print(f"  model_version:       {bundle.model_version}")
        print(f"  model_checksum:      {bundle.model_checksum}")
        print(f"  dataset_version:     {bundle.dataset_version}")
        print(f"  feature_set_id:      {bundle.feature_set_id}")
        print(f"  final_report_status: {bundle.final_report_status}")
        print(f"  training_set_size:   {bundle.training_set_size}")

        if bundle.final_report_status != "VALIDATED FOR INTERNAL RESEARCH":
            print(
                f"  WARNING: final_report_status is '{bundle.final_report_status}', "
                "not the expected 'VALIDATED FOR INTERNAL RESEARCH'. This is not "
                "itself a failure (the registry is the source of truth for status), "
                "but confirm this is the model you intended to deploy.",
                file=sys.stderr,
            )

    if not overall_ok:
        print("Refusing to proceed. This deployment step must not continue.", file=sys.stderr)
        return 1

    print(f"\nAll {len(endpoints)} registered endpoint(s) passed integrity verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
