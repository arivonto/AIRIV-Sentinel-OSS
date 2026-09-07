from pathlib import Path

import pytest

from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    ProductionTargetMode,
    SystemdAttemptFact,
    SystemdProductionTargetPolicy,
    SystemdProductionTargetRule,
    SystemdVerificationRequirements,
    protected_target,
    validate_unit_name,
)


def autonomous_rule(
    unit="airiv-demo-worker.service",
    **kwargs,
):
    return SystemdProductionTargetRule(
        unit=unit,
        mode=ProductionTargetMode.AUTONOMOUS,
        **kwargs,
    )


def test_default_policy_has_empty_allowlist():
    policy = SystemdProductionTargetPolicy()

    assert dict(policy.rules) == {}

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert result.target_known is False
    assert result.autonomous_eligible is False
    assert result.reasons == ("target_not_allowlisted",)


@pytest.mark.parametrize(
    "unit",
    [
        "*.service",
        "worker-?.service",
        "worker[1].service",
        "worker@1.service",
        "worker.socket",
        "worker.target",
        "worker.timer",
        "worker.mount",
        "worker",
        "",
        " worker.service",
        "worker.service ",
    ],
)
def test_non_exact_or_non_service_targets_fail_closed(unit):
    with pytest.raises((TypeError, ValueError)):
        validate_unit_name(unit)


@pytest.mark.parametrize(
    "unit",
    [
        "airiv-sentinel.service",
        "airiv-sentinel-remediation-canary.service",
        "dbus.service",
        "polkit.service",
        "ssh.service",
        "sshd.service",
        "NetworkManager.service",
        "networking.service",
        "ufw.service",
        "firewalld.service",
        "nftables.service",
        "systemd-journald.service",
        "systemd-logind.service",
        "systemd-networkd.service",
        "systemd-resolved.service",
    ],
)
def test_protected_targets_are_non_overrideable(unit):
    assert protected_target(unit) is True

    with pytest.raises(ValueError):
        SystemdProductionTargetPolicy(
            [
                SystemdProductionTargetRule(
                    unit=unit,
                    mode=ProductionTargetMode.AUTONOMOUS,
                )
            ]
        )


def test_exact_allowlisted_autonomous_target_is_eligible():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert result.target_known is True
    assert result.protected_target is False
    assert result.autonomous_eligible is True
    assert result.commander_required is False
    assert result.cooldown_satisfied is True
    assert result.retry_budget_available is True
    assert result.blast_radius_available is True
    assert result.reasons == (
        "autonomous_target_safety_satisfied",
    )


def test_similar_name_does_not_match_exact_allowlist():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker-2.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert result.target_known is False
    assert result.autonomous_eligible is False


@pytest.mark.parametrize(
    "action",
    [
        "START",
        "STOP",
        "RELOAD",
        "ENABLE",
        "DISABLE",
        "MASK",
        "UNMASK",
        "KILL",
        "restart",
        "",
    ],
)
def test_only_exact_restart_action_is_supported(action):
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=action,
        now=1000.0,
    )

    assert result.autonomous_eligible is False
    assert result.reasons == ("unsupported_action",)


def test_commander_only_target_never_becomes_autonomous():
    policy = SystemdProductionTargetPolicy(
        [
            SystemdProductionTargetRule(
                unit="airiv-accounting.service",
                mode=ProductionTargetMode.COMMANDER_ONLY,
            )
        ]
    )

    result = policy.assess(
        unit="airiv-accounting.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert result.target_known is True
    assert result.commander_required is True
    assert result.autonomous_eligible is False
    assert "commander_required" in result.reasons


def test_cooldown_blocks_autonomous_eligibility():
    policy = SystemdProductionTargetPolicy(
        [
            autonomous_rule(
                cooldown_seconds=300.0,
                retry_window_seconds=1000.0,
                max_attempts_per_window=10,
            )
        ]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=[
            SystemdAttemptFact(
                unit="airiv-demo-worker.service",
                action=ACTION_RESTART,
                timestamp=900.0,
            )
        ],
    )

    assert result.cooldown_satisfied is False
    assert result.autonomous_eligible is False
    assert "cooldown_active" in result.reasons


def test_cooldown_expiry_restores_that_gate():
    policy = SystemdProductionTargetPolicy(
        [
            autonomous_rule(
                cooldown_seconds=300.0,
                retry_window_seconds=1000.0,
                max_attempts_per_window=10,
            )
        ]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1200.0,
        attempts=[
            SystemdAttemptFact(
                unit="airiv-demo-worker.service",
                action=ACTION_RESTART,
                timestamp=900.0,
            )
        ],
    )

    assert result.cooldown_satisfied is True


def test_retry_budget_blocks_autonomous_eligibility():
    policy = SystemdProductionTargetPolicy(
        [
            autonomous_rule(
                cooldown_seconds=10.0,
                retry_window_seconds=900.0,
                max_attempts_per_window=1,
            )
        ]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=[
            SystemdAttemptFact(
                unit="airiv-demo-worker.service",
                action=ACTION_RESTART,
                timestamp=500.0,
            )
        ],
    )

    assert result.cooldown_satisfied is True
    assert result.retry_budget_available is False
    assert result.autonomous_eligible is False
    assert "retry_budget_exhausted" in result.reasons


def test_attempts_for_other_targets_do_not_consume_budget():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=[
            SystemdAttemptFact(
                unit="unrelated.service",
                action=ACTION_RESTART,
                timestamp=999.0,
            )
        ],
    )

    assert result.autonomous_eligible is True


def test_future_attempt_fails_closed():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    with pytest.raises(ValueError):
        policy.assess(
            unit="airiv-demo-worker.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=[
                SystemdAttemptFact(
                    unit="airiv-demo-worker.service",
                    action=ACTION_RESTART,
                    timestamp=1001.0,
                )
            ],
        )


def test_existing_production_effect_blocks_blast_radius():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
        active_production_effects=1,
    )

    assert result.blast_radius_available is False
    assert result.autonomous_eligible is False
    assert "production_effect_already_active" in result.reasons


@pytest.mark.parametrize("active", [-1, 1.0, "1"])
def test_invalid_concurrency_fact_fails_closed(active):
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    with pytest.raises(ValueError):
        policy.assess(
            unit="airiv-demo-worker.service",
            action=ACTION_RESTART,
            now=1000.0,
            active_production_effects=active,
        )


def test_verification_requirements_cannot_be_weakened():
    with pytest.raises(ValueError):
        autonomous_rule(
            verification=SystemdVerificationRequirements(
                require_loaded=True,
                require_active=True,
                require_invocation_id_change=False,
            )
        )


def test_default_verification_requires_invocation_change():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert result.verification is not None
    assert result.verification.require_loaded is True
    assert result.verification.require_active is True
    assert result.verification.require_invocation_id_change is True


def test_duplicate_rules_rejected():
    rule = autonomous_rule()

    with pytest.raises(ValueError):
        SystemdProductionTargetPolicy([rule, rule])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cooldown_seconds": 0},
        {"cooldown_seconds": -1},
        {"retry_window_seconds": 0},
        {"retry_window_seconds": -1},
        {"max_attempts_per_window": 0},
        {"max_attempts_per_window": -1},
    ],
)
def test_invalid_rule_limits_rejected(kwargs):
    with pytest.raises(ValueError):
        autonomous_rule(**kwargs)


def test_module_has_no_execution_or_privilege_surface():
    source = (
        Path(__file__).resolve().parents[1]
        / "sentinel"
        / "systemd_production_target_policy.py"
    ).read_text(encoding="utf-8")

    prohibited = (
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "systemd-run",
        "os.system",
        "shell=True",
    )

    for token in prohibited:
        assert token not in source


def test_assessment_does_not_expose_allow_deny_authority():
    policy = SystemdProductionTargetPolicy(
        [autonomous_rule()]
    )

    result = policy.assess(
        unit="airiv-demo-worker.service",
        action=ACTION_RESTART,
        now=1000.0,
    )

    assert not hasattr(result, "decision")
    assert not hasattr(result, "allow")
    assert not hasattr(result, "deny")
    assert not hasattr(result, "execute")
