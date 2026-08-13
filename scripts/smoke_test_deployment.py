#!/usr/bin/env python3
"""Post-deployment smoke tests. Phase 8 Sec 15.

Runs against a live, already-deployed instance (local, staging, or
production) via plain HTTP -- no test framework, no fixtures, no access to
the deployment's internals. This is deliberately the same kind of check an
external uptime monitor would run: if this script cannot pass against a
deployment, that deployment is not ready, regardless of what the test
suite said at build time.

Checks, in order (Sec 15's list):
    1. Frontend loads
    2. API responds (liveness)
    3. Database is reachable (via /health/ready)
    4. Model loads (via /health/ready)
    5. A known test molecule produces the expected qualitative behaviour
    6. Uncertainty is returned
    7. Applicability domain is returned
    8. Errors are handled correctly (a malformed request gets a clean 4xx,
       never a fabricated prediction)

Exact floating-point values are deliberately NOT asserted (Sec 15: "do not
compare against fragile exact floating-point values unless appropriate")
-- qualitative shape and category only, the same philosophy as the
scientific regression suite (tests/golden/test_herg_model_regression.py).

Usage:
    python scripts/smoke_test_deployment.py --api-url http://localhost:8000 [--frontend-url http://localhost] [--api-key KEY]

Exit code 0 if every check passes, 1 otherwise. Prints a pass/fail line
per check so a CI log shows exactly what failed.
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
import json as jsonlib


class SmokeTestFailure(Exception):
    pass


def _get(url: str, headers: dict | None = None, timeout: float = 10.0):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 -- trusted, operator-supplied URL
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post(url: str, body: dict, headers: dict | None = None, timeout: float = 15.0):
    data = jsonlib.dumps(body).encode("utf-8")
    req_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def check_frontend_loads(frontend_url: str) -> None:
    status, body = _get(frontend_url)
    if status != 200:
        msg = f"frontend returned {status}, expected 200"
        raise SmokeTestFailure(msg)
    if b"DrugSim" not in body and b"drugsim" not in body.lower():
        msg = "frontend response did not contain any recognisable DrugSim content"
        raise SmokeTestFailure(msg)


def check_api_responds(api_url: str) -> None:
    status, body = _get(f"{api_url}/health")
    if status != 200:
        msg = f"/health returned {status}, expected 200"
        raise SmokeTestFailure(msg)
    payload = jsonlib.loads(body)
    if payload.get("status") != "ok":
        msg = f"/health body was {payload!r}, expected status=ok"
        raise SmokeTestFailure(msg)


def check_database_and_model_ready(api_url: str) -> None:
    status, body = _get(f"{api_url}/health/ready")
    payload = jsonlib.loads(body)
    checks = payload.get("checks", {})
    if checks.get("database") != "ok":
        msg = f"database health check reported: {checks.get('database')!r}"
        raise SmokeTestFailure(msg)
    if checks.get("model") != "ok":
        msg = f"model health check reported: {checks.get('model')!r}"
        raise SmokeTestFailure(msg)
    if checks.get("prediction_engine") != "ok":
        msg = f"prediction_engine health check reported: {checks.get('prediction_engine')!r}"
        raise SmokeTestFailure(msg)
    if status != 200:
        msg = f"/health/ready returned {status} despite all checks reporting ok -- inconsistent response"
        raise SmokeTestFailure(msg)


#: Ethanol -- the same fixed, always-parseable molecule used by the
#: prediction-engine health check (api.py's _HEALTH_CHECK_SMILES). Using
#: the same one here means a smoke-test failure and a health-check failure
#: point at the same evidence.
_TEST_SMILES = "CCO"


def check_known_molecule_prediction(api_url: str, headers: dict) -> dict:
    status, body = _post(f"{api_url}/predict", {"structure": {"format": "smiles", "value": _TEST_SMILES}}, headers)
    if status != 200:
        msg = f"prediction for a known-good molecule returned {status}, expected 200: {body[:300]!r}"
        raise SmokeTestFailure(msg)
    payload = jsonlib.loads(body)
    if payload.get("estimate", {}).get("predicted_label") not in ("blocker", "non_blocker"):
        msg = f"predicted_label was not a recognised value: {payload.get('estimate')!r}"
        raise SmokeTestFailure(msg)
    return payload


def check_uncertainty_present(payload: dict) -> None:
    conformal = payload.get("reliability", {}).get("conformal", {})
    if not conformal.get("predicted_set"):
        msg = f"conformal.predicted_set missing or empty: {conformal!r}"
        raise SmokeTestFailure(msg)
    if not isinstance(conformal.get("nominal_confidence"), (int, float)):
        msg = f"conformal.nominal_confidence missing or not numeric: {conformal!r}"
        raise SmokeTestFailure(msg)


def check_applicability_domain_present(payload: dict) -> None:
    ad = payload.get("reliability", {}).get("applicability_domain", {})
    if ad.get("verdict") not in ("in_domain", "borderline", "out_of_domain", "undeterminable"):
        msg = f"applicability_domain.verdict was not a recognised value: {ad!r}"
        raise SmokeTestFailure(msg)
    if not ad.get("rationale"):
        msg = f"applicability_domain.rationale missing: {ad!r}"
        raise SmokeTestFailure(msg)


def check_every_servable_endpoint(api_url: str, headers: dict) -> None:
    """Phase 10 fix: the original smoke test only ever exercised the
    implicit default (hERG) endpoint via ``/predict`` -- a deployment could
    have a completely broken second endpoint (CYP3A4, or any future one)
    and this script would still print "All smoke tests passed." This walks
    ``GET /endpoints`` and runs a real prediction against every endpoint it
    reports as servable, so a broken non-default endpoint fails the gate
    instead of shipping silently. Labels are checked generically (some
    plausible string was returned) rather than against hERG's specific
    blocker/non_blocker vocabulary, since other endpoints use their own.
    """
    status, body = _get(f"{api_url}/endpoints", headers)
    if status != 200:
        msg = f"/endpoints returned {status}, expected 200: {body[:300]!r}"
        raise SmokeTestFailure(msg)
    endpoints = jsonlib.loads(body).get("endpoints", [])
    servable = [e for e in endpoints if e.get("servable")]
    if not servable:
        msg = "GET /endpoints reported zero servable endpoints -- nothing would be available to users"
        raise SmokeTestFailure(msg)

    for endpoint in servable:
        model_id = endpoint["model_id"]
        status, body = _post(
            f"{api_url}/predict",
            {"structure": {"format": "smiles", "value": _TEST_SMILES}, "endpoint": model_id},
            headers,
        )
        if status != 200:
            msg = f"endpoint {model_id!r}: prediction for a known-good molecule returned {status}, expected 200: {body[:300]!r}"
            raise SmokeTestFailure(msg)
        payload = jsonlib.loads(body)
        if payload.get("estimate", {}).get("endpoint") != model_id:
            msg = f"endpoint {model_id!r}: response reported endpoint={payload.get('estimate', {}).get('endpoint')!r}"
            raise SmokeTestFailure(msg)
        if not payload.get("estimate", {}).get("predicted_label"):
            msg = f"endpoint {model_id!r}: predicted_label missing"
            raise SmokeTestFailure(msg)
        check_uncertainty_present(payload)
        check_applicability_domain_present(payload)


def check_errors_handled_correctly(api_url: str, headers: dict) -> None:
    # Malformed structure -> clean 422 problem+json, never a fabricated result.
    status, body = _post(api_url + "/predict", {"structure": {"format": "smiles", "value": ""}}, headers)
    if status != 422:
        msg = f"an empty structure returned {status}, expected 422"
        raise SmokeTestFailure(msg)
    payload = jsonlib.loads(body)
    if "estimate" in payload:
        msg = "an error response unexpectedly contained a fabricated 'estimate' field"
        raise SmokeTestFailure(msg)

    # Nonexistent prediction id -> clean 404.
    status, _ = _get(f"{api_url}/predict/prd_00000000000000000000000000", headers)
    if status != 404:
        msg = f"a nonexistent prediction id returned {status}, expected 404"
        raise SmokeTestFailure(msg)


CHECKS = [
    ("frontend loads", lambda ctx: check_frontend_loads(ctx["frontend_url"])),
    ("API responds", lambda ctx: check_api_responds(ctx["api_url"])),
    ("database and model are ready", lambda ctx: check_database_and_model_ready(ctx["api_url"])),
    ("known molecule produces a valid prediction", lambda ctx: ctx.__setitem__("_payload", check_known_molecule_prediction(ctx["api_url"], ctx["headers"]))),
    ("uncertainty is returned", lambda ctx: check_uncertainty_present(ctx["_payload"])),
    ("applicability domain is returned", lambda ctx: check_applicability_domain_present(ctx["_payload"])),
    ("every servable endpoint produces a valid prediction", lambda ctx: check_every_servable_endpoint(ctx["api_url"], ctx["headers"])),
    ("errors are handled correctly", lambda ctx: check_errors_handled_correctly(ctx["api_url"], ctx["headers"])),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of the prediction API")
    parser.add_argument("--frontend-url", default=None, help="Base URL of the frontend (skipped if omitted)")
    parser.add_argument("--api-key", default=None, help="X-API-Key header value, if the deployment requires one")
    args = parser.parse_args()

    headers = {"X-API-Key": args.api_key} if args.api_key else {}
    ctx = {"api_url": args.api_url.rstrip("/"), "frontend_url": args.frontend_url, "headers": headers}

    checks = CHECKS if args.frontend_url else CHECKS[1:]

    failures = 0
    for name, check in checks:
        try:
            check(ctx)
        except SmokeTestFailure as exc:
            print(f"FAIL: {name} -- {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001 -- any unexpected exception is also a smoke-test failure
            print(f"FAIL: {name} -- unexpected error: {type(exc).__name__}: {exc}")
            failures += 1
        else:
            print(f"PASS: {name}")

    if not args.frontend_url:
        print("SKIPPED: frontend loads -- no --frontend-url given")

    print()
    if failures:
        print(f"{failures} smoke test(s) FAILED. This deployment is not ready.")
        return 1

    print("All smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
