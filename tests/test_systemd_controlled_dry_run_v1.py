from __future__ import annotations

from dataclasses import replace

import pytest

from sentinel.resource_bound_remediation import (
    build_bound_systemd_remediation_plan,
)
from sentinel.runtime import (
    SentinelRuntime,
)
from sentinel.systemd_controlled_dry_run import (
    POLKIT_MANAGE_UNITS,
    SystemdControlledDryRun,
    SystemdPrivilegePreflight,
    inspect_systemd_privilege,
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


class Completed:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


class FakeRunner:
    def __init__(
        self,
        *,
        sudo_rc=1,
        pkcheck_rc=1,
    ):
        self.sudo_rc = sudo_rc
        self.pkcheck_rc = pkcheck_rc
        self.calls = []

    def __call__(
        self,
        argv,
        **kwargs,
    ):
        argv = tuple(argv)

        self.calls.append(
            (
                argv,
                kwargs,
            )
        )

        if argv[-2:] == (
            "-n",
            "true",
        ):
            return Completed(
                self.sudo_rc
            )

        if "--action-id" in argv:
            return Completed(
                self.pkcheck_rc
            )

        raise AssertionError(
            f"unexpected command: {argv!r}"
        )


def identity():
    return SystemdUnitIdentity(
        manager=SystemdManagerIdentity(
            boot_id=BOOT_ID,
            manager_pid=1,
            manager_start_ticks=123456,
        ),

        unit_name="airiv-sentinel.service",

        fragment_path=(
            "/etc/systemd/system/"
            "airiv-sentinel.service"
        ),

        fragment_sha256="a" * 64,

        fragment_device=100,
        fragment_inode=200,

        fragment_uid=0,
        fragment_gid=0,
    )


def plan(
    *,
    run_id="RUN-D6B",
    execution_id="EXEC-D6B",
    permit_id="PERMIT-D6B",
):
    target = identity()

    before = SystemdUnitSnapshot(
        identity=target,

        load_state="loaded",
        active_state="active",
        sub_state="running",
        unit_file_state="enabled",

        main_pid=1000,

        invocation_id="a" * 32,

        exec_main_start_timestamp_monotonic=100000,
    )

    scope = BoundSystemdActionScope(
        target=target,

        operation=SystemdOperation.RESTART,

        privilege=SystemdPrivilegeBoundary(
            systemctl_binary="/usr/bin/systemctl"
        ),

        expected_pre_active_state="active",
        expected_post_active_state="active",

        require_new_invocation=True,
    )

    return build_bound_systemd_remediation_plan(
        before=before,
        scope=scope,

        run_id=run_id,

        incident_id="INC-D6B",

        action=ACTION,

        execution_id=execution_id,
        permit_id=permit_id,
    )


def runtime(
    tmp_path,
    monkeypatch,
):
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

    return SentinelRuntime()


def privilege(
    candidate,
    *,
    result="DENIED",
):
    return SystemdPrivilegePreflight(
        component_id=(
            candidate.effect.component_id
        ),

        target_fingerprint=(
            candidate.effect.target_fingerprint
        ),

        scope_fingerprint=(
            candidate.effect.scope_fingerprint
        ),

        effect_fingerprint=(
            candidate.effect.fingerprint
        ),

        argv=tuple(
            candidate.effect.argv
        ),

        uid=1000,
        gid=1000,

        systemctl_binary="/usr/bin/systemctl",

        polkit_action_id=(
            POLKIT_MANAGE_UNITS
        ),

        sudo_noninteractive="DENIED",

        polkit_noninteractive=result,

        result=result,
    )


def test_pkcheck_noninteractive_omits_interaction_flag():
    candidate = plan()

    runner = FakeRunner(
        sudo_rc=1,
        pkcheck_rc=1,
    )

    result = inspect_systemd_privilege(
        plan=candidate,
        runner=runner,
    )

    assert result.result == "DENIED"

    calls = [
        argv
        for argv, _kwargs
        in runner.calls
        if "--action-id" in argv
    ]

    assert len(calls) == 1

    argv = calls[0]

    assert POLKIT_MANAGE_UNITS in argv

    assert (
        "--allow-user-interaction"
        not in argv
    )

    assert not any(
        value.startswith(
            "--allow-user-interaction="
        )
        for value in argv
    )


def test_direct_polkit_authorization_is_required():
    candidate = plan()

    result = inspect_systemd_privilege(
        plan=candidate,

        runner=FakeRunner(
            sudo_rc=0,
            pkcheck_rc=1,
        ),
    )

    assert (
        result.sudo_noninteractive
        == "AUTHORIZED"
    )

    assert (
        result.polkit_noninteractive
        == "DENIED"
    )

    assert result.result == "DENIED"

    assert not result.live_authorized


def test_polkit_authorized_is_live_authorized():
    candidate = plan()

    result = inspect_systemd_privilege(
        plan=candidate,

        runner=FakeRunner(
            sudo_rc=1,
            pkcheck_rc=0,
        ),
    )

    assert result.result == "AUTHORIZED"
    assert result.live_authorized


def test_privilege_fingerprint_binds_result():
    candidate = plan()

    denied = privilege(
        candidate,
        result="DENIED",
    )

    authorized = replace(
        denied,

        polkit_noninteractive="AUTHORIZED",
        result="AUTHORIZED",
    )

    assert (
        denied.fingerprint
        != authorized.fingerprint
    )


def test_privilege_binding_rejects_other_effect(
    tmp_path,
    monkeypatch,
):
    rt = runtime(
        tmp_path,
        monkeypatch,
    )

    first = plan(
        run_id="RUN-A",
    )

    second = plan(
        run_id="RUN-B",
        execution_id="EXEC-B",
        permit_id="PERMIT-B",
    )

    with pytest.raises(
        PermissionError,
        match="privilege_preflight_binding_mismatch",
    ):
        SystemdControlledDryRun(
            rt
        ).run(
            plan=first,
            privilege=privilege(second),
        )


def test_activation_is_temporary_and_hard_stops(
    tmp_path,
    monkeypatch,
):
    rt = runtime(
        tmp_path,
        monkeypatch,
    )

    candidate = plan()

    allowed_object = (
        rt.policy.allowed_actions
    )

    entries_object = (
        rt.remediation_action_catalog
        ._entries
    )

    trigger_object = (
        rt.remediation_action_catalog
        ._trigger_map
    )

    assert rt.policy.allowed_actions == set()
    assert rt.policy.list_bound_runs() == ()

    result = (
        SystemdControlledDryRun(
            rt
        ).run(
            plan=candidate,

            privilege=privilege(
                candidate
            ),
        )
    )

    assert result.policy_decision == "ALLOW"

    assert (
        result.policy_reason
        == "exact_bound_effect_authorized"
    )

    assert result.action_visible
    assert result.bound_run_visible
    assert result.catalog_visible

    assert result.hard_stopped
    assert result.state_restored

    assert (
        rt.policy.allowed_actions
        is allowed_object
    )

    assert (
        rt.remediation_action_catalog
        ._entries
        is entries_object
    )

    assert (
        rt.remediation_action_catalog
        ._trigger_map
        is trigger_object
    )

    assert rt.policy.allowed_actions == set()
    assert rt.policy.list_bound_runs() == ()

    assert (
        rt.remediation_action_catalog
        .list_actions()
        == ()
    )

    boundary = (
        rt.commander
        .remediation_orchestrator
        .identity_boundary
    )

    assert (
        boundary.journal
        .get_live_run_permit(
            candidate.effect.policy_run_id
        )
        is None
    )

    assert (
        boundary.journal
        .get(
            candidate.effect.execution_id
        )
        is None
    )


def test_denied_privilege_remains_fail_closed(
    tmp_path,
    monkeypatch,
):
    rt = runtime(
        tmp_path,
        monkeypatch,
    )

    candidate = plan(
        run_id="RUN-DENIED",
        execution_id="EXEC-DENIED",
        permit_id="PERMIT-DENIED",
    )

    result = (
        SystemdControlledDryRun(
            rt
        ).run(
            plan=candidate,

            privilege=privilege(
                candidate,
                result="DENIED",
            ),
        )
    )

    assert not result.privilege.live_authorized
    assert result.hard_stopped


def test_second_runtime_stays_empty(
    tmp_path,
    monkeypatch,
):
    first = runtime(
        tmp_path / "first",
        monkeypatch,
    )

    candidate = plan(
        run_id="RUN-FIRST",
        execution_id="EXEC-FIRST",
        permit_id="PERMIT-FIRST",
    )

    SystemdControlledDryRun(
        first
    ).run(
        plan=candidate,
        privilege=privilege(candidate),
    )

    second = runtime(
        tmp_path / "second",
        monkeypatch,
    )

    assert second.policy.allowed_actions == set()
    assert second.policy.list_bound_runs() == ()

    assert (
        second.remediation_action_catalog
        .list_actions()
        == ()
    )
