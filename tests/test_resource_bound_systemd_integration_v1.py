from __future__ import annotations

import dataclasses
import subprocess

import pytest

from sentinel.remediation_policy import (
    RemediationPolicy,
)
from sentinel.resource_bound_remediation import (
    GenericBoundRemediationEffect,
    ResourceBoundPermitBinding,
    build_bound_systemd_remediation_plan,
    configure_and_evaluate_bound_policy,
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


def make_identity(
    *,
    digest="a" * 64,
):
    manager = (
        SystemdManagerIdentity(
            boot_id=BOOT,
            manager_pid=1,
            manager_start_ticks=123456,
        )
    )

    return SystemdUnitIdentity(
        manager=manager,

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
):
    return SystemdUnitSnapshot(
        identity=(
            target
            or make_identity()
        ),

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


def make_scope(
    *,
    target=None,
):
    return BoundSystemdActionScope(
        target=(
            target
            or make_identity()
        ),

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


def make_plan():
    target = make_identity()

    return (
        build_bound_systemd_remediation_plan(
            before=make_snapshot(
                target=target
            ),

            scope=make_scope(
                target=target
            ),

            run_id="RUN-D3",

            incident_id="INC-D3",

            action=ACTION,

            execution_id="EXEC-D3",

            permit_id="PERMIT-D3",
        )
    )


def test_generic_effect_is_frozen():
    effect = (
        make_plan()
        .effect
    )

    with pytest.raises(
        dataclasses.FrozenInstanceError
    ):
        effect.action = "evil"


def test_systemd_plan_binds_exact_component():
    plan = make_plan()

    assert (
        plan.effect.component_id
        == "systemd:airiv-sentinel.service"
    )

    assert (
        plan.effect.resource_kind
        == "systemd.service"
    )


def test_systemd_plan_binds_exact_target():
    plan = make_plan()

    assert (
        plan.effect.target_fingerprint
        == plan.scope.target.fingerprint
    )

    assert (
        plan.effect.target
        is plan.scope.target
    )


def test_systemd_plan_binds_exact_scope():
    plan = make_plan()

    assert (
        plan.effect.scope_fingerprint
        == plan.scope.fingerprint
    )


def test_systemd_plan_binds_exact_argv():
    plan = make_plan()

    assert plan.effect.argv == (
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        "airiv-sentinel.service",
    )

    assert (
        plan.effect.argv
        is plan.scope.argv
        or plan.effect.argv
        == plan.scope.argv
    )


def test_effect_fingerprint_changes_on_execution_id():
    plan = make_plan()

    changed = (
        GenericBoundRemediationEffect(
            run_id=plan.effect.run_id,

            incident_id=(
                plan.effect.incident_id
            ),

            component_id=(
                plan.effect.component_id
            ),

            resource_kind=(
                plan.effect.resource_kind
            ),

            target=(
                plan.effect.target
            ),

            scope_fingerprint=(
                plan.effect.scope_fingerprint
            ),

            action=(
                plan.effect.action
            ),

            argv=(
                plan.effect.argv
            ),

            execution_id=(
                "EXEC-DIFFERENT"
            ),

            permit_id=(
                plan.effect.permit_id
            ),
        )
    )

    assert (
        changed.fingerprint
        != plan.effect.fingerprint
    )


def test_effect_fingerprint_changes_on_target():
    plan = make_plan()

    changed_target = (
        make_identity(
            digest="b" * 64
        )
    )

    changed = (
        GenericBoundRemediationEffect(
            run_id=plan.effect.run_id,

            incident_id=(
                plan.effect.incident_id
            ),

            component_id=(
                changed_target.component_id
            ),

            resource_kind=(
                plan.effect.resource_kind
            ),

            target=changed_target,

            scope_fingerprint=(
                plan.effect.scope_fingerprint
            ),

            action=plan.effect.action,

            argv=plan.effect.argv,

            execution_id=(
                plan.effect.execution_id
            ),

            permit_id=(
                plan.effect.permit_id
            ),
        )
    )

    assert (
        changed.fingerprint
        != plan.effect.fingerprint
    )


def test_permit_binding_matches_exact_effect():
    plan = make_plan()

    assert (
        plan.permit_binding
        .matches(
            plan.effect
        )
    )

    assert (
        plan.permit_binding
        .effect_fingerprint
        == plan.effect.fingerprint
    )

    assert (
        plan.permit_binding
        .target_fingerprint
        == plan.effect.target_fingerprint
    )

    assert (
        plan.permit_binding
        .scope_fingerprint
        == plan.scope.fingerprint
    )


def test_permit_binding_rejects_effect_substitution():
    plan = make_plan()

    changed = (
        GenericBoundRemediationEffect(
            run_id=plan.effect.run_id,
            incident_id=plan.effect.incident_id,
            component_id=plan.effect.component_id,

            resource_kind=plan.effect.resource_kind,

            target=plan.effect.target,

            scope_fingerprint=(
                plan.effect.scope_fingerprint
            ),

            action=plan.effect.action,
            argv=plan.effect.argv,

            execution_id="EXEC-OTHER",

            permit_id=plan.effect.permit_id,
        )
    )

    assert not (
        plan.permit_binding
        .matches(
            changed
        )
    )


def test_snapshot_target_substitution_fails_closed():
    before = make_snapshot()

    foreign = make_identity(
        digest="b" * 64
    )

    with pytest.raises(
        ValueError,
        match="snapshot_scope_target_mismatch",
    ):
        build_bound_systemd_remediation_plan(
            before=before,

            scope=make_scope(
                target=foreign
            ),

            run_id="RUN-D3",
            incident_id="INC-D3",
            action=ACTION,
            execution_id="EXEC-D3",
            permit_id="PERMIT-D3",
        )


def test_unexpected_pre_state_fails_closed():
    target = make_identity()

    before = SystemdUnitSnapshot(
        identity=target,

        load_state="loaded",
        active_state="failed",
        sub_state="failed",
        unit_file_state="enabled",

        main_pid=0,

        invocation_id=(
            "02c882ce80f649e0a11beb74a966576b"
        ),

        exec_main_start_timestamp_monotonic=(
            100000
        ),
    )

    with pytest.raises(
        ValueError,
        match="unexpected_systemd_pre_state",
    ):
        build_bound_systemd_remediation_plan(
            before=before,

            scope=make_scope(
                target=target
            ),

            run_id="RUN-D3",
            incident_id="INC-D3",
            action=ACTION,
            execution_id="EXEC-D3",
            permit_id="PERMIT-D3",
        )


def test_existing_remediation_policy_accepts_generic_bound_effect():
    plan = make_plan()

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    decision = (
        configure_and_evaluate_bound_policy(
            policy=policy,

            incident_state=(
                "INVESTIGATING"
            ),

            effect=plan.effect,
        )
    )

    assert decision is not None

    assert (
        plan.effect.run_id
        in policy.list_bound_runs()
    )


def test_policy_rejects_unconfigured_action():
    plan = make_plan()

    policy = RemediationPolicy()

    with pytest.raises(
        RuntimeError,
        match="action_not_temporarily_allowed",
    ):
        configure_and_evaluate_bound_policy(
            policy=policy,

            incident_state=(
                "INVESTIGATING"
            ),

            effect=plan.effect,
        )


def test_no_subprocess_in_plan_or_policy_path(
    monkeypatch,
):
    def forbidden(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "D3 must not execute subprocess"
        )

    monkeypatch.setattr(
        subprocess,
        "run",
        forbidden,
    )

    plan = make_plan()

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    decision = (
        configure_and_evaluate_bound_policy(
            policy=policy,

            incident_state="INVESTIGATING",

            effect=plan.effect,
        )
    )

    assert decision is not None


def test_permit_binding_creation_claims_nothing():
    plan = make_plan()

    binding = (
        ResourceBoundPermitBinding
        .from_effect(
            plan.effect
        )
    )

    assert (
        binding.permit_id
        == "PERMIT-D3"
    )

    assert len(
        binding.fingerprint
    ) == 64
