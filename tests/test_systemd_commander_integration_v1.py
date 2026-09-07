from __future__ import annotations

import ast
import inspect
import subprocess
import time

import pytest

import sentinel.systemd_commander_integration as integration_module

from sentinel.execution import (
    ExecutionResult,
)
from sentinel.resource_bound_remediation import (
    build_bound_systemd_remediation_plan,
)
from sentinel.runtime import (
    SentinelRuntime,
)
from sentinel.systemd_commander_integration import (
    SystemdCommanderIntegration,
)
from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdManagerIdentity,
    SystemdOperation,
    SystemdPrivilegeBoundary,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


ACTION = "systemd_restart"

BOOT_ID = (
    "11111111-2222-3333-4444-555555555555"
)


class FakeArgvExecutor:
    def __init__(
        self,
        *,
        success=True,
    ):
        self.success = success
        self.calls = []
        self.expected_command = None

    def execute_argv(
        self,
        argv,
        timeout=5.0,
    ):
        argv = tuple(
            argv
        )

        self.calls.append(
            (
                argv,
                timeout,
            )
        )

        if (
            self.expected_command
            is None
        ):
            raise AssertionError(
                "canonical command not configured"
            )

        now = time.time()

        return ExecutionResult(
            command=self.expected_command,

            stdout=(
                "FAKE_SYSTEMD_RESTART_OK"
                if self.success
                else ""
            ),

            stderr=(
                ""
                if self.success
                else "FAKE_FAILURE"
            ),

            exit_code=(
                0
                if self.success
                else 1
            ),

            started_at=now,
            finished_at=now,
        )


class SnapshotProvider:
    def __init__(
        self,
        snapshot,
    ):
        self.snapshot = snapshot
        self.calls = 0

    def __call__(
        self,
    ):
        self.calls += 1
        return self.snapshot


def make_identity(
    *,
    digest="a" * 64,
):
    return SystemdUnitIdentity(
        manager=(
            SystemdManagerIdentity(
                boot_id=BOOT_ID,
                manager_pid=1,
                manager_start_ticks=123456,
            )
        ),

        unit_name=(
            "airiv-sentinel.service"
        ),

        fragment_path=(
            "/etc/systemd/system/"
            "airiv-sentinel.service"
        ),

        fragment_sha256=digest,

        fragment_device=100,
        fragment_inode=200,

        fragment_uid=0,
        fragment_gid=0,
    )


def make_snapshot(
    *,
    target=None,
    active_state="active",
    invocation_id="a" * 32,
    main_pid=1000,
    start_monotonic=100000,
):
    target = (
        target
        or make_identity()
    )

    return SystemdUnitSnapshot(
        identity=target,

        load_state="loaded",

        active_state=active_state,

        sub_state=(
            "running"
            if active_state == "active"
            else "failed"
        ),

        unit_file_state="enabled",

        main_pid=main_pid,

        invocation_id=invocation_id,

        exec_main_start_timestamp_monotonic=(
            start_monotonic
        ),
    )


def make_plan(
    *,
    run_id="RUN-D5B",
    execution_id="EXEC-D5B",
    permit_id="PERMIT-D5B",
):
    target = make_identity()

    before = make_snapshot(
        target=target,
        invocation_id="a" * 32,
        main_pid=1000,
        start_monotonic=100000,
    )

    scope = BoundSystemdActionScope(
        target=target,

        operation=(
            SystemdOperation.RESTART
        ),

        privilege=(
            SystemdPrivilegeBoundary(
                systemctl_binary=(
                    "/usr/bin/systemctl"
                )
            )
        ),

        expected_pre_active_state="active",
        expected_post_active_state="active",

        require_new_invocation=True,
    )

    return (
        build_bound_systemd_remediation_plan(
            before=before,

            scope=scope,

            run_id=run_id,

            incident_id="INC-D5B",

            action=ACTION,

            execution_id=execution_id,

            permit_id=permit_id,
        )
    )


def make_runtime(
    tmp_path,
    monkeypatch,
    *,
    executor_success=True,
):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(
            tmp_path
            / "diagnostic"
        ),
    )

    monkeypatch.setenv(
        "AIRIV_SENTINEL_EXECUTION_IDENTITY_DIR",
        str(
            tmp_path
            / "execution"
        ),
    )

    monkeypatch.setenv(
        "AIRIV_SENTINEL_RUNTIME_DIR",
        str(
            tmp_path
            / "runtime"
        ),
    )

    runtime = SentinelRuntime()

    orchestrator = (
        runtime.commander
        .remediation_orchestrator
    )

    fake = FakeArgvExecutor(
        success=executor_success
    )

    orchestrator.gate.executor = fake

    integration = (
        SystemdCommanderIntegration(
            runtime.commander
        )
    )

    return (
        runtime,
        orchestrator,
        fake,
        integration,
    )


def activate_exact_plan(
    runtime,
    plan,
):
    runtime.policy.allowed_actions.add(
        ACTION
    )

    runtime.policy.configure_bound_effect(
        plan.effect
    )


def configure_fake(
    orchestrator,
    fake,
    plan,
):
    fake.expected_command = (
        orchestrator.identity_boundary
        ._bound_command(
            plan.effect
        )
    )


def successful_after(
    plan,
):
    return make_snapshot(
        target=plan.scope.target,

        active_state="active",

        invocation_id="b" * 32,

        main_pid=1001,

        start_monotonic=200000,
    )


def test_uses_canonical_commander_owned_authorities(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    assert (
        integration.commander
        is runtime.commander
    )

    assert (
        integration.policy
        is runtime.policy
    )

    assert (
        integration.execution_adapter
        .identity_boundary
        is orchestrator.identity_boundary
    )

    assert (
        orchestrator.identity_boundary.gate
        is orchestrator.gate
    )


def test_exact_allow_executes_once_and_verifies_recovery(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan()

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    provider = SnapshotProvider(
        successful_after(
            plan
        )
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state=(
                "INVESTIGATING"
            ),

            after_snapshot_provider=(
                provider
            ),

            timeout=3.0,
        )
    )

    assert result.authorization.authorized

    assert result.execution is not None
    assert result.execution.success

    assert (
        result.identity_record
        is not None
    )

    assert (
        result.identity_record.state
        == "SUCCEEDED"
    )

    assert result.replayed is False

    assert (
        result.verification
        is not None
    )

    assert result.verification.verified

    assert (
        result.verification.reason
        == "verified"
    )

    assert result.recovered

    assert provider.calls == 1

    assert len(
        fake.calls
    ) == 1

    argv, timeout = fake.calls[0]

    assert argv == plan.effect.argv
    assert timeout == 3.0


def test_deny_claims_no_permit_and_executes_nothing(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-DENY",
        execution_id="EXEC-D5B-DENY",
        permit_id="PERMIT-D5B-DENY",
    )

    # Base action is allowed but exact bound run is absent.
    runtime.policy.allowed_actions.add(
        ACTION
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    provider = SnapshotProvider(
        successful_after(
            plan
        )
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                provider
            ),
        )
    )

    assert not result.authorization.authorized
    assert result.execution is None
    assert result.identity_record is None
    assert result.verification is None
    assert result.after is None
    assert not result.recovered

    assert fake.calls == []
    assert provider.calls == 0

    permit = (
        orchestrator.identity_boundary
        .journal
        .get_live_run_permit(
            plan.effect.policy_run_id
        )
    )

    assert permit is None

    assert (
        orchestrator.identity_boundary
        .journal
        .get(
            plan.effect.execution_id
        )
        is None
    )


def test_execution_failure_does_not_run_recovery_verifier(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
        executor_success=False,
    )

    plan = make_plan(
        run_id="RUN-D5B-EXECFAIL",
        execution_id="EXEC-D5B-EXECFAIL",
        permit_id="PERMIT-D5B-EXECFAIL",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    provider = SnapshotProvider(
        successful_after(
            plan
        )
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=provider,
        )
    )

    assert result.authorization.authorized
    assert result.execution is not None
    assert not result.execution.success

    assert (
        result.identity_record.state
        == "FAILED"
    )

    assert result.verification is None
    assert result.after is None
    assert not result.recovered

    assert provider.calls == 0

    assert len(
        fake.calls
    ) == 1


def test_same_invocation_fails_verification(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-SAMEINV",
        execution_id="EXEC-D5B-SAMEINV",
        permit_id="PERMIT-D5B-SAMEINV",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    after = make_snapshot(
        target=plan.scope.target,

        active_state="active",

        invocation_id="a" * 32,

        main_pid=1001,

        start_monotonic=200000,
    )

    provider = SnapshotProvider(
        after
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=provider,
        )
    )

    assert result.execution_succeeded

    assert (
        result.verification
        is not None
    )

    assert not result.verification.verified

    assert (
        result.verification.reason
        == "systemd_invocation_not_changed"
    )

    assert not result.recovered

    assert provider.calls == 1


def test_inactive_post_state_fails_verification(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-INACTIVE",
        execution_id="EXEC-D5B-INACTIVE",
        permit_id="PERMIT-D5B-INACTIVE",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    after = make_snapshot(
        target=plan.scope.target,

        active_state="failed",

        invocation_id="b" * 32,

        main_pid=0,

        start_monotonic=200000,
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                SnapshotProvider(
                    after
                )
            ),
        )
    )

    assert result.execution_succeeded

    assert (
        result.verification
        is not None
    )

    assert not result.verification.verified

    assert (
        result.verification.reason
        == "post_restart_not_active"
    )

    assert not result.recovered


def test_target_identity_drift_fails_verification(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-DRIFT",
        execution_id="EXEC-D5B-DRIFT",
        permit_id="PERMIT-D5B-DRIFT",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    foreign = make_identity(
        digest="b" * 64
    )

    after = make_snapshot(
        target=foreign,

        active_state="active",

        invocation_id="b" * 32,

        main_pid=1001,

        start_monotonic=200000,
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                SnapshotProvider(
                    after
                )
            ),
        )
    )

    assert result.execution_succeeded

    assert (
        result.verification
        is not None
    )

    assert not result.verification.verified

    assert (
        result.verification.reason
        == "systemd_target_identity_changed"
    )

    assert not result.recovered


def test_post_snapshot_must_be_canonical_snapshot(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-BADSNAP",
        execution_id="EXEC-D5B-BADSNAP",
        permit_id="PERMIT-D5B-BADSNAP",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    with pytest.raises(
        TypeError,
        match=(
            "after_snapshot_provider must return "
            "SystemdUnitSnapshot"
        ),
    ):
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                lambda: {
                    "ActiveState": "active"
                }
            ),
        )

    # Effect occurred only through fake executor.
    assert len(
        fake.calls
    ) == 1


def test_policy_is_evaluated_exactly_once(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-ONEPOLICY",
        execution_id="EXEC-D5B-ONEPOLICY",
        permit_id="PERMIT-D5B-ONEPOLICY",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    original = (
        runtime.policy.evaluate_bound
    )

    count = {
        "value": 0
    }

    def counted(
        *,
        incident_state,
        effect,
    ):
        count["value"] += 1

        return original(
            incident_state=incident_state,
            effect=effect,
        )

    monkeypatch.setattr(
        runtime.policy,
        "evaluate_bound",
        counted,
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                SnapshotProvider(
                    successful_after(
                        plan
                    )
                )
            ),
        )
    )

    assert result.recovered

    assert count["value"] == 1


def test_fake_path_never_calls_subprocess(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        orchestrator,
        fake,
        integration,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D5B-NOSUBPROC",
        execution_id="EXEC-D5B-NOSUBPROC",
        permit_id="PERMIT-D5B-NOSUBPROC",
    )

    activate_exact_plan(
        runtime,
        plan,
    )

    configure_fake(
        orchestrator,
        fake,
        plan,
    )

    def forbidden(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "subprocess forbidden in D5B"
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        forbidden,
    )

    result = (
        integration.execute_verified(
            plan=plan,

            incident_state="INVESTIGATING",

            after_snapshot_provider=(
                SnapshotProvider(
                    successful_after(
                        plan
                    )
                )
            ),
        )
    )

    assert result.recovered
    assert len(fake.calls) == 1


def test_integration_source_contains_no_host_mutation_authority():
    source = inspect.getsource(
        integration_module
    )

    tree = ast.parse(
        source
    )

    imports = {
        (
            node.module
            if isinstance(
                node,
                ast.ImportFrom,
            )
            else alias.name
        )
        for node in ast.walk(tree)
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
            ),
        )
        for alias in (
            node.names
            if isinstance(
                node,
                ast.Import,
            )
            else [
                type(
                    "Alias",
                    (),
                    {
                        "name":
                            node.module
                    },
                )()
            ]
        )
    }

    assert "subprocess" not in imports
    assert "os" not in imports

    assert "systemctl" not in source
    assert "sudo" not in source
    assert "pkexec" not in source

    attrs = [
        node.attr
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.Attribute,
        )
    ]

    assert (
        "claim_live_run_permit"
        not in attrs
    )

    assert "claim" not in attrs
    assert "transition" not in attrs
    assert "resolve" not in attrs

    # One existing generic adapter is the only effect delegation.
    assert attrs.count(
        "execute"
    ) == 1
