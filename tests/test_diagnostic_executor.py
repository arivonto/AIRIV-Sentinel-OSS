from datetime import datetime

import pytest

from sentinel.diagnostic.executor import DiagnosticExecutor
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
)


def make_action(
    *,
    action_id="diag-exec-001",
    classification=DiagnosticActionClassification.OBSERVE,
    command="printf 'diagnostic-ok'",
):
    return DiagnosticAction(
        diagnostic_action_id=action_id,
        investigation_id="inv-001",
        incident_id="inc-001",
        classification=classification,
        command=command,
        rationale="test diagnostic execution",
        expected_information="command output",
    )


def test_observe_action_executes_and_returns_result():
    result = DiagnosticExecutor().execute(make_action())

    assert result.diagnostic_action_id == "diag-exec-001"
    assert result.command == "printf 'diagnostic-ok'"
    assert result.stdout == "diagnostic-ok"
    assert result.stderr == ""
    assert result.exit_code == 0
    assert result.success is True
    assert result.state == "COMPLETED"
    assert isinstance(result.started_at, datetime)
    assert isinstance(result.finished_at, datetime)


def test_diagnostic_action_executes():
    result = DiagnosticExecutor().execute(
        make_action(
            classification=DiagnosticActionClassification.DIAGNOSTIC,
            command="printf 'hypothesis-test'",
        )
    )

    assert result.stdout == "hypothesis-test"
    assert result.success is True
    assert result.state == "COMPLETED"


def test_failed_diagnostic_command_is_recorded_not_hidden():
    result = DiagnosticExecutor().execute(
        make_action(
            command="printf 'failure-output'; printf 'error-output' >&2; exit 7",
        )
    )

    assert result.stdout == "failure-output"
    assert result.stderr == "error-output"
    assert result.exit_code == 7
    assert result.success is False
    assert result.state == "COMPLETED"


def test_nonexistent_command_result_is_preserved():
    result = DiagnosticExecutor().execute(
        make_action(
            command="command_that_does_not_exist_airiv_sentinel",
        )
    )

    assert result.success is False
    assert result.exit_code != 0
    assert result.state == "COMPLETED"
    assert result.stderr


def test_consequential_action_is_rejected_before_execution():
    action = make_action(
        classification=DiagnosticActionClassification.CONSEQUENTIAL,
        command="touch /tmp/airiv-should-not-exist",
    )

    with pytest.raises(
        ValueError,
        match="action_classification_not_executable",
    ):
        DiagnosticExecutor().execute(action)


def test_prohibited_action_is_rejected_before_execution():
    action = make_action(
        classification=DiagnosticActionClassification.PROHIBITED,
        command="touch /tmp/airiv-should-not-exist",
    )

    with pytest.raises(
        ValueError,
        match="action_classification_not_executable",
    ):
        DiagnosticExecutor().execute(action)


def test_consequential_command_has_not_been_executed():
    marker = "/tmp/airiv-diagnostic-executor-safety-marker"
    action = make_action(
        classification=DiagnosticActionClassification.CONSEQUENTIAL,
        command=f"touch {marker}",
    )

    with pytest.raises(ValueError):
        DiagnosticExecutor().execute(action)

    import os

    assert not os.path.exists(marker)


def test_executor_exposes_no_remediation_authority():
    executor = DiagnosticExecutor()

    assert not hasattr(executor, "remediate")
    assert not hasattr(executor, "authorize")
    assert not hasattr(executor, "resolve")
    assert not hasattr(executor, "execute_remediation")
    assert not hasattr(executor, "execution_boundary")


def test_executor_has_no_incident_lifecycle_authority():
    executor = DiagnosticExecutor()

    assert not hasattr(executor, "create_incident")
    assert not hasattr(executor, "resolve_incident")
    assert not hasattr(executor, "close_incident")


def test_executor_has_no_budget_reset_authority():
    executor = DiagnosticExecutor()

    assert not hasattr(executor, "reset_budget")
    assert not hasattr(executor, "extend_budget")


def test_action_identity_is_preserved():
    result = DiagnosticExecutor().execute(
        make_action(action_id="diag-identity-777")
    )

    assert result.diagnostic_action_id == "diag-identity-777"


def test_executor_does_not_mutate_action():
    action = make_action()
    original_id = action.diagnostic_action_id
    original_command = action.command
    original_classification = action.classification

    DiagnosticExecutor().execute(action)

    assert action.diagnostic_action_id == original_id
    assert action.command == original_command
    assert action.classification == original_classification
