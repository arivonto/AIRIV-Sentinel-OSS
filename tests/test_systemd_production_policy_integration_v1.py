from __future__ import annotations

import inspect

import pytest

from sentinel.remediation_policy import RemediationPolicy
from sentinel.resource_bound_remediation import (
    build_bound_systemd_remediation_plan,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    ProductionTargetMode,
    SystemdAttemptFact,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
)
from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdManagerIdentity,
    SystemdOperation,
    SystemdPrivilegeBoundary,
    SystemdUnitIdentity,
    SystemdUnitSnapshot,
)


LEGACY_ACTION = "systemd_restart"

BOOT_ID = (
    "11111111-2222-3333-4444-555555555555"
)


def make_identity(
    unit="airiv-demo-worker.service",
):
    return SystemdUnitIdentity(
        manager=SystemdManagerIdentity(
            boot_id=BOOT_ID,
            manager_pid=1,
            manager_start_ticks=123456,
        ),
        unit_name=unit,
        fragment_path=(
            "/etc/systemd/system/"
            + unit
        ),
        fragment_sha256="a" * 64,
        fragment_device=100,
        fragment_inode=200,
        fragment_uid=0,
        fragment_gid=0,
    )


def make_plan(
    *,
    unit="airiv-demo-worker.service",
    action=LEGACY_ACTION,
    run_id="RUN-D8-2",
    execution_id="EXEC-D8-2",
    permit_id="PERMIT-D8-2",
):
    target = make_identity(
        unit=unit
    )

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
            systemctl_binary=(
                "/usr/bin/systemctl"
            )
        ),
        expected_pre_active_state="active",
        expected_post_active_state="active",
        require_new_invocation=True,
    )

    return build_bound_systemd_remediation_plan(
        before=before,
        scope=scope,
        run_id=run_id,
        incident_id="INC-D8-2",
        action=action,
        execution_id=execution_id,
        permit_id=permit_id,
    )


def bound_allow_policy(
    plan,
):
    policy = RemediationPolicy(
        {plan.effect.action}
    )

    policy.configure_bound_effect(
        plan.effect
    )

    return policy


def autonomous_targets(
    *,
    unit="airiv-demo-worker.service",
    cooldown_seconds=300.0,
    retry_window_seconds=900.0,
    max_attempts_per_window=1,
):
    return SystemdProductionTargetPolicy(
        [
            SystemdProductionTargetRule(
                unit=unit,
                mode=(
                    ProductionTargetMode.AUTONOMOUS
                ),
                cooldown_seconds=(
                    cooldown_seconds
                ),
                retry_window_seconds=(
                    retry_window_seconds
                ),
                max_attempts_per_window=(
                    max_attempts_per_window
                ),
            )
        ]
    )


def evaluate(
    policy,
    plan,
    *,
    now=1000.0,
    attempts=(),
    active_production_effects=0,
):
    return policy.evaluate_systemd_production_bound(
        incident_state="INVESTIGATING",
        effect=plan.effect,
        now=now,
        attempts=attempts,
        active_production_effects=(
            active_production_effects
        ),
    )


def test_default_production_policy_is_empty():
    policy = RemediationPolicy()

    assert (
        policy.list_systemd_production_targets()
        == ()
    )


def test_empty_target_policy_restricts_exact_bound_allow():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert not authorization.authorized
    assert (
        authorization.reason
        == (
            "production_target_safety_denied:"
            "target_not_allowlisted"
        )
    )

    assert assessment.target_known is False


def test_exact_autonomous_target_preserves_canonical_allow():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert authorization.authorized
    assert (
        authorization.reason
        == "exact_bound_effect_authorized"
    )

    assert assessment.target_known
    assert assessment.autonomous_eligible
    assert assessment.action == ACTION_RESTART


def test_canonical_deny_cannot_be_upgraded():
    plan = make_plan()

    policy = RemediationPolicy()

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert not authorization.authorized
    assert (
        authorization.reason
        == "canonical_policy_denied"
    )

    assert assessment.autonomous_eligible


def test_commander_only_is_denied_from_autonomous_path():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        SystemdProductionTargetPolicy(
            [
                SystemdProductionTargetRule(
                    unit=(
                        "airiv-demo-worker.service"
                    ),
                    mode=(
                        ProductionTargetMode
                        .COMMANDER_ONLY
                    ),
                )
            ]
        )
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert not authorization.authorized
    assert assessment.commander_required

    assert (
        authorization.reason
        == (
            "production_target_safety_denied:"
            "commander_required"
        )
    )


def test_cooldown_restricts_bound_allow():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets(
            cooldown_seconds=300.0,
            retry_window_seconds=1000.0,
            max_attempts_per_window=10,
        )
    )

    authorization, assessment = evaluate(
        policy,
        plan,
        now=1000.0,
        attempts=[
            SystemdAttemptFact(
                unit=(
                    "airiv-demo-worker.service"
                ),
                action=ACTION_RESTART,
                timestamp=900.0,
            )
        ],
    )

    assert not authorization.authorized
    assert not assessment.cooldown_satisfied
    assert "cooldown_active" in assessment.reasons


def test_retry_budget_restricts_bound_allow():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets(
            cooldown_seconds=10.0,
            retry_window_seconds=900.0,
            max_attempts_per_window=1,
        )
    )

    authorization, assessment = evaluate(
        policy,
        plan,
        now=1000.0,
        attempts=[
            SystemdAttemptFact(
                unit=(
                    "airiv-demo-worker.service"
                ),
                action=ACTION_RESTART,
                timestamp=500.0,
            )
        ],
    )

    assert not authorization.authorized
    assert not assessment.retry_budget_available
    assert (
        "retry_budget_exhausted"
        in assessment.reasons
    )


def test_blast_radius_restricts_bound_allow():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    authorization, assessment = evaluate(
        policy,
        plan,
        active_production_effects=1,
    )

    assert not authorization.authorized
    assert not assessment.blast_radius_available
    assert (
        "production_effect_already_active"
        in assessment.reasons
    )


def test_similar_target_does_not_match():
    plan = make_plan(
        unit="airiv-demo-worker-2.service"
    )

    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets(
            unit="airiv-demo-worker.service"
        )
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert not authorization.authorized
    assert assessment.target_known is False


def test_systemd_restart_translation_is_exact():
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert authorization.authorized
    assert assessment.action == "RESTART"


def test_other_action_is_not_translated():
    plan = make_plan(
        action="other_restart"
    )

    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert not authorization.authorized
    assert (
        assessment.reasons
        == ("unsupported_action",)
    )


def test_target_configuration_does_not_add_allowed_action():
    policy = RemediationPolicy()

    before = set(
        policy.allowed_actions
    )

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    assert policy.allowed_actions == before


def test_clear_restores_default_empty_target_policy():
    policy = RemediationPolicy()

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    assert (
        policy.list_systemd_production_targets()
        == (
            "airiv-demo-worker.service",
        )
    )

    policy.clear_systemd_production_target_policy()

    assert (
        policy.list_systemd_production_targets()
        == ()
    )


def test_invalid_target_policy_type_rejected():
    policy = RemediationPolicy()

    with pytest.raises(TypeError):
        policy.configure_systemd_production_target_policy(
            object()
        )


def test_protected_canary_cannot_be_added():
    with pytest.raises(ValueError):
        SystemdProductionTargetPolicy(
            [
                SystemdProductionTargetRule(
                    unit=(
                        "airiv-sentinel-remediation-"
                        "canary.service"
                    ),
                    mode=(
                        ProductionTargetMode.AUTONOMOUS
                    ),
                )
            ]
        )


def test_existing_evaluate_bound_called_exactly_once(
    monkeypatch,
):
    plan = make_plan()
    policy = bound_allow_policy(plan)

    policy.configure_systemd_production_target_policy(
        autonomous_targets()
    )

    original = policy.evaluate_bound
    calls = []

    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(
        policy,
        "evaluate_bound",
        counted,
    )

    authorization, assessment = evaluate(
        policy,
        plan,
    )

    assert authorization.authorized
    assert assessment.autonomous_eligible
    assert len(calls) == 1


def test_new_method_has_no_execution_surface():
    source = inspect.getsource(
        RemediationPolicy
        .evaluate_systemd_production_bound
    )

    assert source.count(
        "self.evaluate_bound("
    ) == 1

    prohibited = (
        "execute_argv",
        "subprocess",
        "sudo",
        "pkexec",
        "systemd-run",
        "shell=True",
        "os.system",
    )

    for token in prohibited:
        assert token not in source
