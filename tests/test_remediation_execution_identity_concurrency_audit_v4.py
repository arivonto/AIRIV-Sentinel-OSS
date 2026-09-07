import threading
import time

from sentinel.execution import ExecutionResult
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


class CountingExecutor:
    def __init__(self, delay=0.05, fail=False):
        self.delay = delay
        self.fail = fail
        self.count = 0
        self.lock = threading.Lock()

    def execute(self, command):
        with self.lock:
            self.count += 1

        time.sleep(self.delay)

        now = time.time()

        return ExecutionResult(
            command=command,
            stdout="failed" if self.fail else "ok",
            stderr="error" if self.fail else "",
            exit_code=1 if self.fail else 0,
            started_at=now,
            finished_at=time.time(),
        )


class RaisingExecutor:
    def execute(self, command):
        raise RuntimeError("synthetic execution failure")


def allow_decision():
    return RemediationDecision(
        decision=PolicyDecision.ALLOW,
        reason="action_authorized",
        incident_state="OPEN",
        component_id="component-1",
        action="test-action",
    )


def make_boundary(tmp_path, executor):
    gate = RemediationExecutionGate(executor)

    return RemediationExecutionIdentityBoundary(
        journal=RemediationExecutionIdentityJournal(root=tmp_path),
        gate=gate,
    )


def test_same_execution_id_executes_exactly_once(tmp_path):
    executor = CountingExecutor()
    boundary = make_boundary(tmp_path, executor)

    results = []
    errors = []

    def worker():
        try:
            results.append(
                boundary.execute(
                    execution_id="same-id",
                    incident_id="incident-1",
                    component_id="component-1",
                    action="test-action",
                    command="synthetic",
                    decision=allow_decision(),
                )
            )
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert not errors
    assert len(results) == 8
    assert executor.count == 1

    fresh = [item for item in results if item[2] is False]
    replayed = [item for item in results if item[2] is True]

    assert len(fresh) == 1
    assert len(replayed) == 7

    records = [item[1] for item in results]

    assert all(
        record.state == ExecutionIdentityState.SUCCEEDED
        for record in records
    )


def test_distinct_execution_ids_execute_independently(tmp_path):
    executor = CountingExecutor()
    boundary = make_boundary(tmp_path, executor)

    results = []

    def worker(index):
        results.append(
            boundary.execute(
                execution_id=f"distinct-{index}",
                incident_id="incident-2",
                component_id="component-1",
                action="test-action",
                command=f"synthetic-{index}",
                decision=allow_decision(),
            )
        )

    threads = [
        threading.Thread(target=worker, args=(index,))
        for index in range(6)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert executor.count == 6
    assert len(results) == 6
    assert all(item[2] is False for item in results)
    assert all(
        item[1].state == ExecutionIdentityState.SUCCEEDED
        for item in results
    )


def test_execution_failure_becomes_failed_terminal_state(tmp_path):
    executor = CountingExecutor(fail=True)
    boundary = make_boundary(tmp_path, executor)

    result, record, replayed = boundary.execute(
        execution_id="failed-execution",
        incident_id="incident-3",
        component_id="component-1",
        action="test-action",
        command="synthetic-failure",
        decision=allow_decision(),
    )

    assert replayed is False
    assert result is not None
    assert result.success is False
    assert record.state == ExecutionIdentityState.FAILED
    assert record.execution is not None


def test_execution_exception_becomes_unknown(tmp_path):
    boundary = make_boundary(
        tmp_path,
        RaisingExecutor(),
    )

    try:
        boundary.execute(
            execution_id="exception-execution",
            incident_id="incident-4",
            component_id="component-1",
            action="test-action",
            command="synthetic-exception",
            decision=allow_decision(),
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    record = RemediationExecutionIdentityJournal(
        root=tmp_path
    ).get("exception-execution")

    assert record is not None
    assert record.state == ExecutionIdentityState.UNKNOWN
    assert record.unknown_reason is not None


def test_unknown_is_not_automatically_retried(tmp_path):
    boundary = make_boundary(
        tmp_path,
        RaisingExecutor(),
    )

    try:
        boundary.execute(
            execution_id="unknown-no-retry",
            incident_id="incident-5",
            component_id="component-1",
            action="test-action",
            command="synthetic-exception",
            decision=allow_decision(),
        )
    except RuntimeError:
        pass

    journal = RemediationExecutionIdentityJournal(root=tmp_path)
    record = journal.get("unknown-no-retry")

    assert record is not None
    assert record.state == ExecutionIdentityState.UNKNOWN

    class ShouldNeverExecute:
        def execute(self, command):
            raise AssertionError(
                "UNKNOWN execution must not be automatically retried"
            )

    retry_boundary = RemediationExecutionIdentityBoundary(
        journal=journal,
        gate=RemediationExecutionGate(
            ShouldNeverExecute()
        ),
    )

    replay_result, replay_record, replayed = retry_boundary.execute(
        execution_id="unknown-no-retry",
        incident_id="incident-5",
        component_id="component-1",
        action="test-action",
        command="must-not-run",
        decision=allow_decision(),
    )

    assert replayed is True
    assert replay_record.state == ExecutionIdentityState.UNKNOWN
    assert replay_result is None


def test_recover_interrupted_claim_and_running_to_unknown(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    journal.claim(
        execution_id="claimed-recovery",
        incident_id="incident-6",
        component_id="component-1",
        action="test-action",
        command="synthetic",
    )

    journal.claim(
        execution_id="running-recovery",
        incident_id="incident-7",
        component_id="component-1",
        action="test-action",
        command="synthetic",
    )

    journal.transition(
        "running-recovery",
        ExecutionIdentityState.RUNNING,
    )

    recovered = journal.recover_interrupted()

    recovered_ids = {
        record.execution_id
        for record in recovered
    }

    assert recovered_ids == {
        "claimed-recovery",
        "running-recovery",
    }

    assert journal.get(
        "claimed-recovery"
    ).state == ExecutionIdentityState.UNKNOWN

    assert journal.get(
        "running-recovery"
    ).state == ExecutionIdentityState.UNKNOWN


def test_terminal_state_cannot_be_changed(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    journal.claim(
        execution_id="terminal-immutable",
        incident_id="incident-8",
        component_id="component-1",
        action="test-action",
        command="synthetic",
    )

    journal.transition(
        "terminal-immutable",
        ExecutionIdentityState.RUNNING,
    )

    journal.transition(
        "terminal-immutable",
        ExecutionIdentityState.SUCCEEDED,
        execution={
            "command": "synthetic",
            "stdout": "ok",
            "stderr": "",
            "exit_code": 0,
            "started_at": 1.0,
            "finished_at": 2.0,
            "success": True,
        },
    )

    try:
        journal.transition(
            "terminal-immutable",
            ExecutionIdentityState.FAILED,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "terminal execution identity must be immutable"
        )

    assert (
        journal.get("terminal-immutable").state
        == ExecutionIdentityState.SUCCEEDED
    )


def test_deny_does_not_consume_execution_identity(tmp_path):
    journal = RemediationExecutionIdentityJournal(root=tmp_path)

    executor = CountingExecutor()
    boundary = RemediationExecutionIdentityBoundary(
        journal=journal,
        gate=RemediationExecutionGate(executor),
    )

    denied = RemediationDecision(
        decision=PolicyDecision.DENY,
        reason="action_not_authorized",
        incident_state="OPEN",
        component_id="component-1",
        action="test-action",
    )

    try:
        boundary.execute(
            execution_id="deny-must-not-consume",
            incident_id="incident-9",
            component_id="component-1",
            action="test-action",
            command="must-not-run",
            decision=denied,
        )
    except ValueError:
        pass

    assert journal.get("deny-must-not-consume") is None
    assert executor.count == 0
