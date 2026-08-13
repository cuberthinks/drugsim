"""Tests for the local validation performed by drugsim_db.audit.audit_context.

These cover only the pre-database validation (malformed user_id, blank reason) —
the actual SET LOCAL / set_config behaviour requires a live session and is covered
by tests/constraints/test_audit_and_triggers.py against a real database.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from drugsim_core.errors import ConfigurationError
from drugsim_core.ids import generate_ulid
from drugsim_db.audit import audit_context

pytestmark = pytest.mark.unit


class TestValidation:
    """Validation that happens before any SQL is issued."""

    def test_malformed_user_id_rejected(self) -> None:
        session = MagicMock()
        with pytest.raises(ConfigurationError, match="valid ULID"):
            with audit_context(session, user_id="not-a-ulid", reason="test"):
                pass
        session.execute.assert_not_called()

    def test_blank_reason_rejected(self) -> None:
        session = MagicMock()
        with pytest.raises(ConfigurationError, match="must not be blank"):
            with audit_context(session, user_id=generate_ulid(), reason="   "):
                pass
        session.execute.assert_not_called()

    def test_empty_reason_rejected(self) -> None:
        session = MagicMock()
        with pytest.raises(ConfigurationError, match="must not be blank"):
            with audit_context(session, user_id=generate_ulid(), reason=""):
                pass

    def test_valid_context_issues_two_statements(self) -> None:
        session = MagicMock()
        with audit_context(session, user_id=generate_ulid(), reason="valid reason"):
            pass
        assert session.execute.call_count == 2

    def test_pipeline_version_adds_a_third_statement(self) -> None:
        session = MagicMock()
        with audit_context(
            session,
            user_id=generate_ulid(),
            reason="ETL run",
            pipeline_version="a" * 40,
        ):
            pass
        assert session.execute.call_count == 3

    def test_reason_passed_as_bound_parameter_not_interpolated(self) -> None:
        """The value must travel as a bind parameter, never string-formatted into SQL.

        String-formatting free-text change_reason into a SET LOCAL statement would
        be a SQL injection vector.
        """
        session = MagicMock()
        malicious = "'; DROP TABLE compound; --"
        with audit_context(session, user_id=generate_ulid(), reason=malicious):
            pass
        # Every call must use set_config with parameters, never the raw reason
        # embedded in the SQL text itself.
        for call in session.execute.call_args_list:
            sql_text = str(call.args[0])
            assert malicious not in sql_text
            assert "set_config" in sql_text.lower()

    def test_yields_control_to_the_caller(self) -> None:
        session = MagicMock()
        sentinel = []
        with audit_context(session, user_id=generate_ulid(), reason="x"):
            sentinel.append(1)
        assert sentinel == [1]
