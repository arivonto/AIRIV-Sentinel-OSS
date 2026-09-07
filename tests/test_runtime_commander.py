from sentinel.commander import CommanderOrchestrator
from sentinel.runtime import SentinelRuntime


def test_runtime_exposes_canonical_commander():
    runtime = SentinelRuntime()

    assert isinstance(runtime.commander, CommanderOrchestrator)
    assert runtime.commander.incident_manager is runtime.incident_manager
    assert runtime.commander.execution is runtime.execution
    assert runtime.commander.remediation_policy is runtime.policy


def test_runtime_commander_uses_runtime_execution_boundary():
    runtime = SentinelRuntime()

    result = runtime.commander.execute_system(
        "printf 'runtime-commander'"
    )

    assert result.execution is not None
    assert result.execution.success
    assert result.execution.stdout == "runtime-commander"
