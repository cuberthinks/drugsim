"""Assert that customer molecular structures never reach log output.

TDS §7.2.3 names five defence layers against structure disclosure via logs and is
explicit that **this test is the layer that actually holds the line** — the others
are defence in depth. A structure in a log line is an IP disclosure into a system
with different access controls, different retention, and wider fan-out than the
database.

If this module fails, the build must not ship.
"""

from __future__ import annotations

import io
import json
import logging
from contextlib import redirect_stdout
from typing import Any

import pytest

from drugsim_core.logging import configure_logging, get_logger, reset_logging
from drugsim_core.redaction import SensitiveStructure

pytestmark = pytest.mark.security

# Real structures. If any of these strings appears in captured output, the test fails.
ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"
IMATINIB = "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1"
CAFFEINE_INCHI = "InChI=1S/C8H10N4O2/c1-10-4-9-6-5(10)7(13)12(3)8(14)11(2)6/h4H,1-3H3"
ASPIRIN_INCHIKEY = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"

SECRET_STRUCTURES = [ASPIRIN, IMATINIB, CAFFEINE_INCHI, ASPIRIN_INCHIKEY]


def _capture_logs(emit: Any) -> str:
    """Run an emitting callable and return everything written to stdout.

    Args:
        emit: Zero-argument callable that emits log records.

    Returns:
        The captured stdout as a single string.
    """
    reset_logging()
    buffer = io.StringIO()
    # The stdlib StreamHandler binds sys.stdout at construction time, so logging must
    # be configured *inside* the redirect for the handler to write to the buffer.
    with redirect_stdout(buffer):
        configure_logging(level="DEBUG", fmt="json")
        emit()
        logging.getLogger().handlers[0].flush()
    reset_logging()
    return buffer.getvalue()


def _assert_clean(output: str) -> None:
    """Assert that no known structure appears in captured output.

    Args:
        output: Captured log output.

    Raises:
        AssertionError: If any secret structure is present.
    """
    for structure in SECRET_STRUCTURES:
        assert structure not in output, (
            f"STRUCTURE DISCLOSURE: {structure[:20]}... appeared in log output. "
            f"This is an IP leak (TDS §7.2.3).\nOutput was:\n{output}"
        )


class TestStructuresNeverReachLogs:
    """Every plausible route by which a structure could reach a log."""

    def test_sensitive_structure_as_keyword(self) -> None:
        """A SensitiveStructure passed as a log field is redacted."""
        def emit() -> None:
            get_logger("t").info("parsing", structure=SensitiveStructure(ASPIRIN))

        _assert_clean(_capture_logs(emit))

    def test_raw_smiles_under_sensitive_key(self) -> None:
        """A raw string under a known sensitive key is redacted."""
        def emit() -> None:
            get_logger("t").info("parsing", smiles=ASPIRIN)

        _assert_clean(_capture_logs(emit))

    def test_raw_smiles_under_arbitrary_key(self) -> None:
        """A raw SMILES under an unexpected key is caught by the pattern backstop."""
        def emit() -> None:
            get_logger("t").warning("odd", some_unexpected_field=IMATINIB)

        _assert_clean(_capture_logs(emit))

    def test_inchi_anywhere_in_message(self) -> None:
        """An InChI embedded in free text is scrubbed."""
        def emit() -> None:
            get_logger("t").info(f"failed to parse {CAFFEINE_INCHI} at step 3")

        _assert_clean(_capture_logs(emit))

    def test_inchikey_in_message(self) -> None:
        """An InChIKey embedded in free text is scrubbed."""
        def emit() -> None:
            get_logger("t").info(f"duplicate detected: {ASPIRIN_INCHIKEY}")

        _assert_clean(_capture_logs(emit))

    def test_structure_nested_in_dict(self) -> None:
        """A structure nested inside a mapping is scrubbed recursively."""
        def emit() -> None:
            get_logger("t").info(
                "batch", payload={"record": {"smiles": ASPIRIN, "index": 4}}
            )

        _assert_clean(_capture_logs(emit))

    def test_structure_nested_in_list(self) -> None:
        """Structures inside a sequence are scrubbed."""
        def emit() -> None:
            get_logger("t").info("batch", smiles_list=[ASPIRIN, IMATINIB])

        _assert_clean(_capture_logs(emit))

    def test_structure_in_exception_traceback(self) -> None:
        """A structure interpolated into an exception message is scrubbed.

        This is the highest-risk real-world path: exception text is formatted and
        logged by handlers far from the raise site, and is easy to overlook.
        """
        def emit() -> None:
            try:
                msg = f"cannot sanitise {ASPIRIN}"
                raise ValueError(msg)
            except ValueError:
                get_logger("t").exception("parse failed")

        _assert_clean(_capture_logs(emit))

    def test_structure_via_stdlib_logging(self) -> None:
        """A structure logged through stdlib logging is scrubbed.

        Third-party libraries use stdlib logging, so the bridge must redact too.
        """
        def emit() -> None:
            logging.getLogger("third_party").warning("processing %s", ASPIRIN)

        _assert_clean(_capture_logs(emit))

    def test_sensitive_structure_in_fstring(self) -> None:
        """f-string interpolation of a SensitiveStructure yields redacted text."""
        structure = SensitiveStructure(ASPIRIN)
        assert ASPIRIN not in f"{structure}"
        assert ASPIRIN not in f"{structure!r}"
        assert ASPIRIN not in f"{structure:>50}"
        assert ASPIRIN not in str(structure)
        assert ASPIRIN not in repr(structure)
        assert ASPIRIN not in "{}".format(structure)  # noqa: UP032


class TestRedactionRemainsUseful:
    """Redaction must not destroy the ability to debug."""

    def test_digest_is_stable_and_correlatable(self) -> None:
        """The same structure yields the same digest, so log lines can be correlated."""
        a = SensitiveStructure(ASPIRIN)
        b = SensitiveStructure(ASPIRIN)
        c = SensitiveStructure(IMATINIB)
        assert a.digest == b.digest
        assert a.digest != c.digest

    def test_digest_appears_in_output(self) -> None:
        """The redacted form carries the digest, preserving traceability."""
        def emit() -> None:
            get_logger("t").info("parsing", smiles=ASPIRIN)

        output = _capture_logs(emit)
        assert "REDACTED" in output
        record = json.loads(output.strip().splitlines()[-1])
        assert "sha256:" in record["smiles"]

    def test_non_structure_fields_survive(self) -> None:
        """Ordinary diagnostic fields are not redacted."""
        def emit() -> None:
            get_logger("t").info(
                "ok",
                compound_uid="01J8XK2M4N7P9QRSTVWXYZ0123",
                endpoint_id="caco2_papp",
                duration_ms=42,
                file_path="/var/data/chembl_37/activities.parquet",
            )

        output = _capture_logs(emit)
        record = json.loads(output.strip().splitlines()[-1])
        assert record["compound_uid"] == "01J8XK2M4N7P9QRSTVWXYZ0123"
        assert record["endpoint_id"] == "caco2_papp"
        assert record["duration_ms"] == 42
        assert record["file_path"] == "/var/data/chembl_37/activities.parquet"

    def test_reveal_is_the_only_route_to_the_value(self) -> None:
        """The raw value remains reachable when explicitly requested."""
        structure = SensitiveStructure(ASPIRIN)
        assert structure.reveal() == ASPIRIN


class TestPredictionApiWiresRedaction:
    """Phase 7 hardening regression test.

    Every test above proves the redaction *mechanism* is correct in
    isolation — none of them prove it is actually active in the running
    prediction service. The Phase 7 audit found that ``drugsim_predict.api``
    never called ``configure_logging()``, so the service ran under
    structlog's unconfigured default and this whole test file's guarantee
    did not actually apply to it. This class pins both the wiring and the
    real end-to-end behaviour so that gap cannot silently reopen.

    Deliberately does NOT use ``importlib.reload(drugsim_predict.api)`` to
    force a fresh module-level ``configure_logging()`` call. Reloading a
    module re-executes its top level in place on the *same* module object,
    which rebinds every module-global name (``app``, ``get_store``, ...) to
    new objects while leaving other already-imported test modules' captured
    references (e.g. ``test_predict_api.py``'s ``from drugsim_predict.api
    import app, get_store``, used as a ``dependency_overrides`` key)
    pointing at the old ones. A handler whose closure looks up ``get_store``
    as a global then resolves to the *new* function object at call time,
    which no longer matches the *old* function object used as the
    dependency-override key elsewhere in the suite — silently routing that
    other test's writes to the real global store instead of its isolated
    one. That is exactly the kind of cross-test corruption a hardening
    regression test must not itself introduce, so the process-import case
    below runs in a subprocess instead, and the exception-safety case below
    patches the already-imported module's globals directly (no reload).
    """

    def test_importing_the_api_module_configures_structlog(self, project_root) -> None:
        """A fresh process importing the API module (exactly what
        ``uvicorn drugsim_predict.api:app`` does) ends with structlog
        configured, i.e. the redaction processor active."""
        import os
        import subprocess
        import sys

        env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
        result = subprocess.run(
            [sys.executable, "-c", "import structlog, drugsim_predict.api; assert structlog.is_configured()"],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    def test_unexpected_exception_during_predict_never_logs_the_structure(self) -> None:
        """An exception whose message happens to embed a real structure
        (as RDKit's own diagnostics sometimes do) must not leak it, even
        though the code path is a generic ``except Exception`` far from any
        deliberate ``SensitiveStructure`` wrapping.

        Patches ``drugsim_predict.api``'s already-imported module globals
        directly and restores them in ``finally`` -- no reload, no lasting
        effect on the shared ``app``/``get_store`` objects other test
        modules hold references to.
        """
        import tempfile
        from pathlib import Path

        from fastapi.testclient import TestClient

        import drugsim_predict.api as api_module
        from drugsim_predict.store import PredictionStore

        db_path = Path(tempfile.mktemp(suffix=".sqlite3"))
        original_run_inference = api_module.run_inference
        original_overrides = dict(api_module.app.dependency_overrides)

        def boom(*_args: object, **_kwargs: object) -> None:
            raise KeyError(f"simulated failure while handling {ASPIRIN}")

        api_module.run_inference = boom  # type: ignore[assignment]
        api_module.app.dependency_overrides[api_module.get_store] = lambda: PredictionStore(db_path=db_path)
        client = TestClient(api_module.app, raise_server_exceptions=False)

        buffer = io.StringIO()
        try:
            reset_logging()
            with redirect_stdout(buffer):
                configure_logging(level="DEBUG", fmt="json")
                client.post("/predict", json={"structure": {"format": "smiles", "value": ASPIRIN}})
                logging.getLogger().handlers[0].flush()
        finally:
            api_module.run_inference = original_run_inference
            api_module.app.dependency_overrides.clear()
            api_module.app.dependency_overrides.update(original_overrides)
            reset_logging()

        _assert_clean(buffer.getvalue())
