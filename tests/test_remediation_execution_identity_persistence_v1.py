from numbers import Real

from sentinel.execution import ExecutionBoundary
from sentinel.remediation_execution_identity import (
    ExecutionIdentityState,
    RemediationExecutionIdentityBoundary,
    RemediationExecutionIdentityJournal,
)
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_policy import (
    PolicyDecision,
    RemediationDecision,
)


def _allow_decision():
    return RemediationDecision(
        decision=PolicyDecision.ALLOW,
        reason="action_authorized",
        incident_state="OPEN",
        component_id="test-component",
        action="test-action",
    )


def test_execution_identity_persists_and_replays(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    boundary = RemediationExecutionIdentityBoundary(
        journal=journal,
        gate=RemediationExecutionGate(ExecutionBoundary()),
    )

    decision = _allow_decision()

    result, record, replayed = boundary.execute(
        execution_id="exec-persistence-regression",
        incident_id="incident-1",
        component_id="test-component",
        action="test-action",
        command="printf 'identity-persistence-ok'",
        decision=decision,
    )

    assert replayed is False
    assert result is not None
    assert record.state == ExecutionIdentityState.SUCCEEDED
    assert record.execution is not None

    assert isinstance(record.execution["started_at"], Real)
    assert isinstance(record.execution["finished_at"], Real)
    assert record.execution["finished_at"] >= record.execution["started_at"]

    assert record.execution["stdout"] == "identity-persistence-ok"

    replay_result, replay_record, replayed_again = boundary.execute(
        execution_id="exec-persistence-regression",
        incident_id="incident-1",
        component_id="test-component",
        action="test-action",
        command="printf 'SHOULD-NOT-RUN'",
        decision=decision,
    )

    assert replayed_again is True
    assert replay_result is not None
    assert replay_record.state == ExecutionIdentityState.SUCCEEDED

    assert isinstance(replay_result.started_at, Real)
    assert isinstance(replay_result.finished_at, Real)
    assert replay_result.finished_at >= replay_result.started_at

    assert replay_result.stdout == "identity-persistence-ok"
    assert "SHOULD-NOT-RUN" not in replay_result.stdout


def test_execution_identity_survives_new_journal_instance(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    boundary = RemediationExecutionIdentityBoundary(
        journal=journal,
        gate=RemediationExecutionGate(ExecutionBoundary()),
    )

    decision = _allow_decision()

    result, record, replayed = boundary.execute(
        execution_id="exec-restart-regression",
        incident_id="incident-2",
        component_id="test-component",
        action="test-action",
        command="printf 'restart-persistence-ok'",
        decision=decision,
    )

    assert result is not None
    assert replayed is False
    assert record.state == ExecutionIdentityState.SUCCEEDED

    new_journal = RemediationExecutionIdentityJournal(root=tmp_path)

    new_boundary = RemediationExecutionIdentityBoundary(
        journal=new_journal,
        gate=RemediationExecutionGate(ExecutionBoundary()),
    )

    replay_result, replay_record, replayed_again = new_boundary.execute(
        execution_id="exec-restart-regression",
        incident_id="incident-2",
        component_id="test-component",
        action="test-action",
        command="printf 'SHOULD-NOT-RUN'",
        decision=decision,
    )

    assert replayed_again is True
    assert replay_record.state == ExecutionIdentityState.SUCCEEDED
    assert replay_result is not None

    assert isinstance(replay_result.started_at, Real)
    assert isinstance(replay_result.finished_at, Real)
    assert replay_result.finished_at >= replay_result.started_at

    assert replay_result.stdout == "restart-persistence-ok"
    assert "SHOULD-NOT-RUN" not in replay_result.stdout


def test_execution_identity_json_record_is_durable(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    boundary = RemediationExecutionIdentityBoundary(
        journal=journal,
        gate=RemediationExecutionGate(ExecutionBoundary()),
    )

    decision = _allow_decision()

    result, record, replayed = boundary.execute(
        execution_id="exec-json-regression",
        incident_id="incident-3",
        component_id="test-component",
        action="test-action",
        command="printf 'json-durable-ok'",
        decision=decision,
    )

    assert result is not None
    assert replayed is False
    assert record.state == ExecutionIdentityState.SUCCEEDED

    persisted = tmp_path / "exec-json-regression" / "record.json"

    assert persisted.exists()
    assert persisted.is_file()
    assert persisted.stat().st_size > 0

    reloaded = RemediationExecutionIdentityJournal(
        root=tmp_path
    ).get("exec-json-regression")

    assert reloaded is not None
    assert reloaded.state == ExecutionIdentityState.SUCCEEDED
    assert reloaded.execution is not None
    assert reloaded.execution["stdout"] == "json-durable-ok"
    assert isinstance(reloaded.execution["started_at"], Real)
    assert isinstance(reloaded.execution["finished_at"], Real)
