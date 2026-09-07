from __future__ import annotations

import json
import subprocess
import time

import pytest

from sentinel.execution import (
    ExecutionResult,
)
from sentinel.generic_execution_permit_adapter import (
    GenericResourceExecutionPermitAdapter,
)
from sentinel.remediation_policy import (
    RemediationPolicy,
)
from sentinel.resource_bound_remediation import (
    build_bound_systemd_remediation_plan,
)
from sentinel.runtime import (
    SentinelRuntime,
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

BOOT = (
    "11111111-2222-3333-4444-555555555555"
)


class FakeArgvExecutor:
    def __init__(self):
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
                "expected canonical command not configured"
            )

        now = time.time()

        return ExecutionResult(
            command=(
                self.expected_command
            ),
            stdout="FAKE_EXECUTION_OK",
            stderr="",
            exit_code=0,
            started_at=now,
            finished_at=now,
        )


def make_identity(
    *,
    digest="a" * 64,
):
    return SystemdUnitIdentity(
        manager=(
            SystemdManagerIdentity(
                boot_id=BOOT,
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


def make_plan(
    *,
    run_id="RUN-D4B",
    execution_id="EXEC-D4B",
    permit_id="PERMIT-D4B",
    digest="a" * 64,
):
    target = make_identity(
        digest=digest
    )

    before = SystemdUnitSnapshot(
        identity=target,

        load_state="loaded",
        active_state="active",
        sub_state="running",
        unit_file_state="enabled",

        main_pid=229612,

        invocation_id=(
            "02c882ce80f649e0a11beb74a966576b"
        ),

        exec_main_start_timestamp_monotonic=(
            100000
        ),
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

            incident_id=(
                "INC-D4B"
            ),

            action=ACTION,

            execution_id=execution_id,
            permit_id=permit_id,
        )
    )


def make_runtime(
    tmp_path,
    monkeypatch,
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

    boundary = (
        runtime.commander
        .remediation_orchestrator
        .identity_boundary
    )

    fake = FakeArgvExecutor()

    # Existing gate remains canonical.
    # Only its lowest external-effect executor is replaced.
    boundary.gate.executor = fake

    adapter = (
        GenericResourceExecutionPermitAdapter(
            boundary
        )
    )

    return (
        runtime,
        boundary,
        fake,
        adapter,
    )


def authorize(
    runtime,
    plan,
):
    runtime.policy.allowed_actions.add(
        ACTION
    )

    runtime.policy.configure_bound_effect(
        plan.effect
    )

    authorization = (
        runtime.policy.evaluate_bound(
            incident_state=(
                "INVESTIGATING"
            ),
            effect=plan.effect,
        )
    )

    assert authorization.authorized

    return authorization


def configure_fake_command(
    boundary,
    fake,
    plan,
):
    fake.expected_command = (
        boundary._bound_command(
            plan.effect
        )
    )


def test_generic_authorization_matches_systemd_effect():
    plan = make_plan()

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    policy.configure_bound_effect(
        plan.effect
    )

    authorization = (
        policy.evaluate_bound(
            incident_state="INVESTIGATING",
            effect=plan.effect,
        )
    )

    assert authorization.authorized

    assert authorization.matches(
        plan.effect
    )


def test_fake_executor_end_to_end_uses_real_permit_and_identity(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan()

    authorization = authorize(
        runtime,
        plan,
    )

    configure_fake_command(
        boundary,
        fake,
        plan,
    )

    result = adapter.execute(
        effect=plan.effect,

        authorization=(
            authorization
        ),

        permit_binding=(
            plan.permit_binding
        ),

        incident_state=(
            "INVESTIGATING"
        ),

        timeout=3.0,
    )

    assert result.replayed is False

    assert result.execution is not None
    assert result.execution.success

    assert (
        result.execution.stdout
        == "FAKE_EXECUTION_OK"
    )

    assert (
        result.identity_record.state
        == "SUCCEEDED"
    )

    assert len(
        fake.calls
    ) == 1

    argv, timeout = (
        fake.calls[0]
    )

    assert (
        argv
        == plan.effect.argv
    )

    assert timeout == 3.0

    permit = (
        boundary.journal
        .get_live_run_permit(
            plan.effect.policy_run_id
        )
    )

    assert permit is not None

    assert (
        permit.run_id
        == plan.effect.policy_run_id
    )

    assert (
        permit.execution_id
        == plan.effect.execution_id
    )

    assert (
        permit.permit_id
        == plan.effect.permit_id
    )

    assert (
        permit.effect_fingerprint
        == plan.effect.fingerprint
    )

    assert (
        permit.target_fingerprint
        == plan.effect.target_fingerprint
    )


def test_exact_replay_does_not_execute_twice(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D4B-REPLAY",
        execution_id="EXEC-D4B-REPLAY",
        permit_id="PERMIT-D4B-REPLAY",
    )

    authorization = authorize(
        runtime,
        plan,
    )

    configure_fake_command(
        boundary,
        fake,
        plan,
    )

    first = adapter.execute(
        effect=plan.effect,
        authorization=authorization,
        permit_binding=plan.permit_binding,
        incident_state="INVESTIGATING",
    )

    second = adapter.execute(
        effect=plan.effect,
        authorization=authorization,
        permit_binding=plan.permit_binding,
        incident_state="INVESTIGATING",
    )

    assert first.replayed is False
    assert second.replayed is True

    assert len(
        fake.calls
    ) == 1

    assert (
        second.identity_record
        == first.identity_record
    )


def test_permit_crash_gap_fails_closed_without_execution(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D4B-CRASH",
        execution_id="EXEC-D4B-CRASH",
        permit_id="PERMIT-D4B-CRASH",
    )

    authorization = authorize(
        runtime,
        plan,
    )

    configure_fake_command(
        boundary,
        fake,
        plan,
    )

    claim = (
        boundary.journal
        .claim_live_run_permit(
            effect=plan.effect,
            authorization=authorization,
        )
    )

    assert claim.replayed is False

    # Deliberately simulate crash between durable permit
    # and execution identity claim.
    assert (
        boundary.journal.get(
            plan.effect.execution_id
        )
        is None
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "live_run_permit_replay_without_"
            "execution_identity"
        ),
    ):
        adapter.execute(
            effect=plan.effect,
            authorization=authorization,
            permit_binding=plan.permit_binding,
            incident_state="INVESTIGATING",
        )

    assert fake.calls == []


def test_same_run_changed_effect_conflicts_before_execution(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    first = make_plan(
        run_id="RUN-D4B-CONFLICT",
        execution_id="EXEC-D4B-A",
        permit_id="PERMIT-D4B-A",
    )

    first_auth = authorize(
        runtime,
        first,
    )

    configure_fake_command(
        boundary,
        fake,
        first,
    )

    result = adapter.execute(
        effect=first.effect,
        authorization=first_auth,
        permit_binding=first.permit_binding,
        incident_state="INVESTIGATING",
    )

    assert result.execution is not None
    assert len(fake.calls) == 1

    # New policy instance can authorize a separately constructed
    # candidate, but the SAME durable journal run must reject it.
    second = make_plan(
        run_id="RUN-D4B-CONFLICT",
        execution_id="EXEC-D4B-B",
        permit_id="PERMIT-D4B-B",
    )

    second_policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    second_policy.configure_bound_effect(
        second.effect
    )

    second_auth = (
        second_policy.evaluate_bound(
            incident_state="INVESTIGATING",
            effect=second.effect,
        )
    )

    assert second_auth.authorized

    fake.expected_command = (
        boundary._bound_command(
            second.effect
        )
    )

    with pytest.raises(
        RuntimeError,
        match="live_run_permit_conflict",
    ):
        adapter.execute(
            effect=second.effect,
            authorization=second_auth,
            permit_binding=second.permit_binding,
            incident_state="INVESTIGATING",
        )

    assert len(fake.calls) == 1


def test_permit_binding_substitution_fails_before_journal(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    first = make_plan(
        run_id="RUN-D4B-BIND-A",
    )

    second = make_plan(
        run_id="RUN-D4B-BIND-B",
        execution_id="EXEC-D4B-BIND-B",
        permit_id="PERMIT-D4B-BIND-B",
    )

    authorization = authorize(
        runtime,
        first,
    )

    configure_fake_command(
        boundary,
        fake,
        first,
    )

    with pytest.raises(
        PermissionError,
        match="resource_permit_binding_mismatch",
    ):
        adapter.execute(
            effect=first.effect,
            authorization=authorization,

            permit_binding=(
                second.permit_binding
            ),

            incident_state="INVESTIGATING",
        )

    assert (
        boundary.journal
        .get_live_run_permit(
            first.effect.policy_run_id
        )
        is None
    )

    assert fake.calls == []


def test_authorization_substitution_fails_before_journal(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    first = make_plan(
        run_id="RUN-D4B-AUTH-A",
    )

    second = make_plan(
        run_id="RUN-D4B-AUTH-B",
        execution_id="EXEC-D4B-AUTH-B",
        permit_id="PERMIT-D4B-AUTH-B",
    )

    authorization = authorize(
        runtime,
        second,
    )

    configure_fake_command(
        boundary,
        fake,
        first,
    )

    with pytest.raises(
        PermissionError,
        match="authorization_effect_binding_mismatch",
    ):
        adapter.execute(
            effect=first.effect,
            authorization=authorization,
            permit_binding=first.permit_binding,
            incident_state="INVESTIGATING",
        )

    assert (
        boundary.journal
        .get_live_run_permit(
            first.effect.policy_run_id
        )
        is None
    )

    assert fake.calls == []


def test_deny_authorization_cannot_claim_permit(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D4B-DENY",
    )

    # Action exists in allowlist but exact run was never configured.
    runtime.policy.allowed_actions.add(
        ACTION
    )

    authorization = (
        runtime.policy.evaluate_bound(
            incident_state="INVESTIGATING",
            effect=plan.effect,
        )
    )

    assert not authorization.authorized

    with pytest.raises(
        PermissionError,
        match=(
            "bound remediation authorization is DENY"
        ),
    ):
        adapter.execute(
            effect=plan.effect,
            authorization=authorization,
            permit_binding=plan.permit_binding,
            incident_state="INVESTIGATING",
        )

    assert (
        boundary.journal
        .get_live_run_permit(
            plan.effect.policy_run_id
        )
        is None
    )

    assert fake.calls == []


def test_no_subprocess_used_by_fake_end_to_end_path(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D4B-NOSUBPROCESS",
        execution_id="EXEC-D4B-NOSUBPROCESS",
        permit_id="PERMIT-D4B-NOSUBPROCESS",
    )

    authorization = authorize(
        runtime,
        plan,
    )

    configure_fake_command(
        boundary,
        fake,
        plan,
    )

    def forbidden(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "subprocess execution forbidden in D4B"
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        forbidden,
    )

    result = adapter.execute(
        effect=plan.effect,
        authorization=authorization,
        permit_binding=plan.permit_binding,
        incident_state="INVESTIGATING",
    )

    assert result.execution is not None
    assert result.execution.success
    assert len(fake.calls) == 1


def test_canonical_command_binding_is_argv_not_shell(
    tmp_path,
    monkeypatch,
):
    (
        runtime,
        boundary,
        fake,
        adapter,
    ) = make_runtime(
        tmp_path,
        monkeypatch,
    )

    plan = make_plan(
        run_id="RUN-D4B-COMMAND",
    )

    authorization = authorize(
        runtime,
        plan,
    )

    configure_fake_command(
        boundary,
        fake,
        plan,
    )

    result = adapter.execute(
        effect=plan.effect,
        authorization=authorization,
        permit_binding=plan.permit_binding,
        incident_state="INVESTIGATING",
    )

    command = (
        result.execution.command
    )

    decoded = json.loads(
        command
    )

    assert tuple(decoded) == (
        plan.effect.argv
    )

    assert decoded == [
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        "airiv-sentinel.service",
    ]
