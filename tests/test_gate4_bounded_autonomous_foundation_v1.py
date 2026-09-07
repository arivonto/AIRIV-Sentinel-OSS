"""Gate 4 bounded autonomous production foundation regression."""

import json
import time

from sentinel.execution import ExecutionResult
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_evidence import TrustedSystemdEvidenceRecord
from sentinel.systemd_incident_dispatch import (
    SystemdDispatchEvidenceIdentity,
    SystemdIncidentDispatchAssessment,
)
from sentinel.systemd_production_bounded_autonomous import (
    ARGV,
    COMPONENT,
    UNIT,
    BoundedAutonomousSystemdCapability,
    invoke_bounded_autonomous_systemd_production,
)
from sentinel.systemd_production_target_policy import ACTION_RESTART
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity,
    SystemdPrivilegeBoundary,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


BOOT_ID = "11111111-2222-3333-4444-555555555555"


class FakeArgvExecutor:
    def __init__(self):
        self.calls = []

    def execute_argv(self, argv, timeout=5.0):
        argv = tuple(argv)
        self.calls.append((argv, timeout))
        command = json.dumps(
            list(argv),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        now = time.time()
        return ExecutionResult(
            command=command,
            stdout="FAKE_GATE4_RESTART_OK",
            stderr="",
            exit_code=0,
            started_at=now,
            finished_at=now,
        )


def target():
    return SystemdUnitIdentity(
        manager=SystemdManagerIdentity(
            boot_id=BOOT_ID,
            manager_pid=1,
            manager_start_ticks=123456,
        ),
        unit_name=UNIT,
        fragment_path=(
            "/etc/systemd/system/"
            "airiv-sentinel-production-remediation-probe.service"
        ),
        fragment_sha256="a" * 64,
        fragment_device=100,
        fragment_inode=200,
        fragment_uid=0,
        fragment_gid=0,
    )


def snapshot(*, invocation, pid, started):
    return SystemdUnitSnapshot(
        identity=target(),
        load_state="loaded",
        active_state="active",
        sub_state="running",
        unit_file_state="enabled",
        main_pid=pid,
        invocation_id=invocation,
        exec_main_start_timestamp_monotonic=started,
    )


def make_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(tmp_path / "execution"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(tmp_path / "runtime"),
    )
    monkeypatch.setenv(
        "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR",
        str(tmp_path / "production-state"),
    )

    runtime = SentinelRuntime()
    fake = FakeArgvExecutor()
    runtime.commander.remediation_orchestrator.gate.executor = fake
    return runtime, fake


def prepared(runtime, before, *, suffix, now):
    incident_id = "gate4-incident-" + suffix
    evidence = TrustedSystemdEvidenceRecord(
        incident_id=incident_id,
        component_id=COMPONENT,
        observation_id="gate4-observation-" + suffix,
        investigation_id="gate4-investigation-" + suffix,
        observed_at=now,
        snapshot=before,
    )
    assessment = SystemdIncidentDispatchAssessment(
        candidate=True,
        incident_id=incident_id,
        component_id=COMPONENT,
        unit=UNIT,
        action=ACTION_RESTART,
        reasons=("gate4_bounded_autonomous_candidate",),
        trusted_evidence_identities=(
            SystemdDispatchEvidenceIdentity.from_record(evidence),
        ),
    )
    return runtime.systemd_production_preparation.prepare(
        assessment=assessment,
        evidence=evidence,
        now=now,
        max_age_seconds=300.0,
        privilege=SystemdPrivilegeBoundary(systemctl_binary=ARGV[0]),
        run_id="gate4-run-" + suffix,
        execution_id="gate4-execution-" + suffix,
        permit_id="gate4-permit-" + suffix,
    )


def assert_runtime_policy_empty(runtime):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()
    assert runtime.policy.list_systemd_production_targets() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()


def test_gate4_defaults_disabled_and_performs_no_execution(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    before = snapshot(invocation="a" * 32, pid=1000, started=100000)
    plan = prepared(runtime, before, suffix="disabled", now=115.0)

    result = invoke_bounded_autonomous_systemd_production(
        capability=BoundedAutonomousSystemdCapability(),
        integration=runtime.systemd_production_integration,
        catalog=runtime.remediation_action_catalog,
        prepared=plan,
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: (_ for _ in ()).throw(
            AssertionError("disabled Gate 4 requested post-state")
        ),
        production_now=115.0,
    )

    assert result.delegated is False
    assert result.reason == "gate4_bounded_autonomous_disabled"
    assert fake.calls == []
    assert_runtime_policy_empty(runtime)


def test_gate4_exact_probe_executes_without_commander_authorization(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    before = snapshot(invocation="a" * 32, pid=1000, started=100000)
    after = snapshot(invocation="b" * 32, pid=1001, started=200000)
    plan = prepared(runtime, before, suffix="success", now=115.0)

    result = invoke_bounded_autonomous_systemd_production(
        capability=BoundedAutonomousSystemdCapability(enabled=True),
        integration=runtime.systemd_production_integration,
        catalog=runtime.remediation_action_catalog,
        prepared=plan,
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: after,
        production_now=115.0,
    )

    assert result.delegated is True
    delegated = result.runtime_result
    assert delegated is not None
    assert delegated.delegated is True
    integration = delegated.integration_result
    assert integration is not None
    assert integration.authorization.authorized is True
    assert integration.execution_succeeded is True
    assert integration.verification_succeeded is True
    assert integration.recovered is True

    assert len(fake.calls) == 1
    argv, timeout = fake.calls[0]
    assert argv == ARGV
    assert timeout == 5.0

    assert_runtime_policy_empty(runtime)

    # Autonomous execution must not manufacture Commander durable evidence.
    gate4_root = tmp_path / "gate4-commander-state-must-not-exist"
    assert not gate4_root.exists()


def test_gate4_durable_attempt_budget_blocks_second_execution(
    tmp_path,
    monkeypatch,
):
    runtime, fake = make_runtime(tmp_path, monkeypatch)
    capability = BoundedAutonomousSystemdCapability(enabled=True)

    first_before = snapshot(
        invocation="a" * 32,
        pid=1000,
        started=100000,
    )
    first_after = snapshot(
        invocation="b" * 32,
        pid=1001,
        started=200000,
    )
    first = prepared(runtime, first_before, suffix="first", now=115.0)

    first_result = invoke_bounded_autonomous_systemd_production(
        capability=capability,
        integration=runtime.systemd_production_integration,
        catalog=runtime.remediation_action_catalog,
        prepared=first,
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: first_after,
        production_now=115.0,
    )

    assert first_result.runtime_result.integration_result.recovered is True
    assert len(fake.calls) == 1
    assert_runtime_policy_empty(runtime)

    second_after = snapshot(
        invocation="c" * 32,
        pid=1002,
        started=300000,
    )
    second = prepared(runtime, first_after, suffix="second", now=116.0)

    second_result = invoke_bounded_autonomous_systemd_production(
        capability=capability,
        integration=runtime.systemd_production_integration,
        catalog=runtime.remediation_action_catalog,
        prepared=second,
        incident_state="INVESTIGATING",
        after_snapshot_provider=lambda: second_after,
        production_now=116.0,
    )

    integration = second_result.runtime_result.integration_result
    assert integration is not None
    assert integration.authorization.authorized is False
    assert integration.execution is None
    assert integration.verification is None
    assert len(fake.calls) == 1
    assert_runtime_policy_empty(runtime)


def test_gate4_rejects_non_probe_capability():
    try:
        BoundedAutonomousSystemdCapability(
            enabled=True,
            unit="some-other.service",
        )
    except ValueError as exc:
        assert str(exc) == "gate4_exact_probe_target_required"
    else:
        raise AssertionError("non-probe Gate 4 target was accepted")
