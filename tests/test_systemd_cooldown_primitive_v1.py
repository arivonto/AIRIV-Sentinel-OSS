"""Tests for the canonical systemd cooldown primitive (Stage 3B)."""

from __future__ import annotations

import math

import pytest

from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    SystemdAttemptFact,
    SystemdCooldownAssessment,
    assess_systemd_cooldown,
)


# --- 1. No attempts → satisfied ---

def test_no_attempts_satisfied():
    result = assess_systemd_cooldown(
        unit="some.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=(),
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is True
    assert result.last_attempt_timestamp is None
    assert result.relevant_attempt_count == 0


# --- 2. Unrelated unit ignored ---

def test_unrelated_unit_ignored():
    attempts = [
        SystemdAttemptFact(unit="other.service", action=ACTION_RESTART, timestamp=100.0)
    ]
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=200.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is True
    assert result.relevant_attempt_count == 0


# --- 3. Unrelated action ignored ---

def test_unrelated_action_ignored():
    attempts = [
        SystemdAttemptFact(unit="target.service", action="STOP", timestamp=100.0)
    ]
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=200.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is True
    assert result.relevant_attempt_count == 0


# --- 4. Relevant attempt < cooldown → not satisfied ---

def test_relevant_attempt_under_cooldown():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=100.0)
    ]
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is False
    assert result.last_attempt_timestamp == 100.0
    assert result.relevant_attempt_count == 1


# --- 5. Relevant attempt exactly at boundary → satisfied ---

def test_relevant_attempt_exactly_at_boundary():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=200.0)
    ]
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=2000.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is True
    assert result.last_attempt_timestamp == 200.0


# --- 6. Relevant attempt > boundary → satisfied ---

def test_relevant_attempt_over_boundary():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=100.0)
    ]
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=3000.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is True


# --- 7. Newest relevant attempt controls decision ---

def test_newest_relevant_attempt_controls():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=100.0),
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=500.0),
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=2200.0),
    ]
    # now=3000, newest=2200, elapsed=800 < 1800 → not satisfied
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=3000.0,
        attempts=attempts,
        cooldown_seconds=1800.0,
    )
    assert result.cooldown_satisfied is False
    assert result.last_attempt_timestamp == 2200.0
    assert result.relevant_attempt_count == 3


# --- 8. Malformed attempt type ---

def test_malformed_attempt_type_raises():
    with pytest.raises(TypeError, match="SystemdAttemptFact"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=["not-an-attempt"],
            cooldown_seconds=1800.0,
        )


# --- 9. Non-finite timestamp ---

def test_non_finite_timestamp_raises():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=math.inf)
    ]
    with pytest.raises(ValueError, match="timestamp must be finite"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=attempts,
            cooldown_seconds=1800.0,
        )


# --- 10. Future timestamp ---

def test_future_timestamp_raises():
    attempts = [
        SystemdAttemptFact(unit="target.service", action=ACTION_RESTART, timestamp=2000.0)
    ]
    with pytest.raises(ValueError, match="future attempt timestamp"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=attempts,
            cooldown_seconds=1800.0,
        )


# --- 11. Invalid now ---

def test_invalid_now_raises():
    with pytest.raises(ValueError, match="now must be finite"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=math.nan,
            attempts=(),
            cooldown_seconds=1800.0,
        )


def test_negative_now_raises():
    with pytest.raises(ValueError, match="now must be non-negative"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=-1.0,
            attempts=(),
            cooldown_seconds=1800.0,
        )


# --- 12. Invalid cooldown_seconds ---

def test_invalid_cooldown_seconds_raises():
    with pytest.raises(ValueError, match="cooldown_seconds"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=(),
            cooldown_seconds=-1.0,
        )


def test_zero_cooldown_seconds_raises():
    with pytest.raises(ValueError, match="cooldown_seconds"):
        assess_systemd_cooldown(
            unit="target.service",
            action=ACTION_RESTART,
            now=1000.0,
            attempts=(),
            cooldown_seconds=0.0,
        )


# --- 13. Protected target remains rejected by policy ---

def test_protected_target_still_rejected_by_policy():
    from sentinel.systemd_production_target_policy import (
        SystemdProductionTargetPolicy,
    )
    policy = SystemdProductionTargetPolicy()
    result = policy.assess(
        unit="airiv-sentinel.service",
        action=ACTION_RESTART,
        now=1000.0,
    )
    assert result.protected_target is True
    assert result.cooldown_satisfied is False
    assert "protected_target" in result.reasons


# --- 14. airiv-sentinel.service remains protected ---

def test_airiv_sentinel_service_protected():
    from sentinel.systemd_production_target_policy import protected_target
    assert protected_target("airiv-sentinel.service") is True


# --- 15. Allowlisted non-protected target behavior unchanged ---

def test_allowlisted_target_cooldown_behavior_unchanged():
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.COMMANDER_ONLY,
        cooldown_seconds=300.0,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])

    # No attempts → cooldown satisfied
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1000.0,
    )
    assert result.cooldown_satisfied is True
    assert result.target_known is True

    # Recent attempt → cooldown not satisfied
    attempts = [
        SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=800.0)
    ]
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=attempts,
    )
    assert result.cooldown_satisfied is False

    # Old attempt → cooldown satisfied
    attempts = [
        SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=100.0)
    ]
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=attempts,
    )
    assert result.cooldown_satisfied is True


# --- 16. Commander-only behavior unchanged ---

def test_commander_only_mode_unchanged():
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.COMMANDER_ONLY,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])
    result = policy.assess(unit="myapp.service", action=ACTION_RESTART, now=1000.0)
    assert result.commander_required is True
    assert "commander_required" in result.reasons


# --- 17. Existing cooldown behavior unchanged ---

def test_existing_cooldown_boundary_semantic():
    """now - last_timestamp >= cooldown_seconds → satisfied."""
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.AUTONOMOUS,
        cooldown_seconds=1800.0,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])

    # Exactly at boundary
    attempts = [
        SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=200.0)
    ]
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=2000.0,
        attempts=attempts,
    )
    assert result.cooldown_satisfied is True

    # One second under boundary
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1999.0,
        attempts=attempts,
    )
    assert result.cooldown_satisfied is False


# --- 18. Existing blast-radius/retry-window behavior unchanged ---

def test_blast_radius_unchanged():
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.AUTONOMOUS,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])

    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1000.0,
        active_production_effects=1,
    )
    assert result.blast_radius_available is False
    assert "production_effect_already_active" in result.reasons


def test_retry_window_unchanged():
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.AUTONOMOUS,
        retry_window_seconds=900.0,
        max_attempts_per_window=1,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])

    # One attempt in window → retry budget exhausted
    attempts = [
        SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=950.0)
    ]
    result = policy.assess(
        unit="myapp.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=attempts,
    )
    assert result.retry_budget_available is False
    assert "retry_budget_exhausted" in result.reasons


# --- 19. Result type and immutability ---

def test_result_is_frozen_dataclass():
    result = assess_systemd_cooldown(
        unit="target.service",
        action=ACTION_RESTART,
        now=1000.0,
        attempts=(),
        cooldown_seconds=1800.0,
    )
    assert isinstance(result, SystemdCooldownAssessment)
    with pytest.raises(AttributeError):
        result.cooldown_satisfied = False


# --- Differential: primitive matches old inline behavior ---

def test_differential_primitive_matches_inline():
    """Primitive produces same cooldown_satisfied as the original inline formula."""
    from sentinel.systemd_production_target_policy import (
        ProductionTargetMode,
        SystemdProductionTargetPolicy,
        SystemdProductionTargetRule,
    )
    rule = SystemdProductionTargetRule(
        unit="myapp.service",
        mode=ProductionTargetMode.AUTONOMOUS,
        cooldown_seconds=1800.0,
    )
    policy = SystemdProductionTargetPolicy(rules=[rule])

    test_cases = [
        (1000.0, []),
        (2000.0, [SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=100.0)]),
        (2000.0, [SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=200.0)]),
        (2000.0, [SystemdAttemptFact(unit="myapp.service", action=ACTION_RESTART, timestamp=199.9)]),
    ]

    for now, attempts in test_cases:
        policy_result = policy.assess(
            unit="myapp.service",
            action=ACTION_RESTART,
            now=now,
            attempts=attempts,
        )
        primitive_result = assess_systemd_cooldown(
            unit="myapp.service",
            action=ACTION_RESTART,
            now=now,
            attempts=attempts,
            cooldown_seconds=1800.0,
        )
        assert policy_result.cooldown_satisfied == primitive_result.cooldown_satisfied, (
            f"Mismatch at now={now}, attempts={attempts}: "
            f"policy={policy_result.cooldown_satisfied}, "
            f"primitive={primitive_result.cooldown_satisfied}"
        )
