"""Tests for Stage 2 deterministic systemd SLO admission classification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentinel.slo_enforcement_frontier import SloEnforcementCandidate
from sentinel.slo_systemd_admission_eligibility import (
    ACTION,
    APPROVED_SCOPE_ID,
    COMPONENT_ID,
    DECISION_ID,
    ELIGIBLE,
    MEASUREMENT_SOURCE_ID,
    SLO_DEFINITION_ID,
    UNIT,
    SloAdmissionResult,
    classify_slo_admission,
)


def _valid_candidate(*, observed_at: datetime | None = None) -> SloEnforcementCandidate:
    return SloEnforcementCandidate(
        decision_id=DECISION_ID,
        approved_scope_id=APPROVED_SCOPE_ID,
        slo_definition_id=SLO_DEFINITION_ID,
        measurement_source_id=MEASUREMENT_SOURCE_ID,
        component_id=COMPONENT_ID,
        target=UNIT,
        consequence=ACTION,
        worker_id="worker-test-1",
        observed_at=observed_at or datetime(2026, 9, 19, tzinfo=timezone.utc),
        age_seconds=3600.0,
    )


def _now() -> datetime:
    return datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)


# --- Initial attempt classification ---


def test_valid_candidate_zero_attempts_eligible():
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=())
    assert result.eligible is True
    assert result.reason == ELIGIBLE


def test_valid_candidate_empty_attempts_eligible():
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=[])
    assert result.eligible is True
    assert result.reason == ELIGIBLE


# --- Prior attempt detection ---


def test_one_prior_relevant_attempt_fails_closed():
    from sentinel.systemd_production_target_policy import (
        ACTION_RESTART,
        SystemdAttemptFact,
    )
    attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 3600,
        )
    ]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is False
    assert result.reason == "retry_evidence_unAVAILABLE"


def test_multiple_prior_relevant_attempts_fails_closed():
    from sentinel.systemd_production_target_policy import (
        ACTION_RESTART,
        SystemdAttemptFact,
    )
    attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 7200,
        ),
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 3600,
        ),
    ]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is False
    assert result.reason == "retry_evidence_unAVAILABLE"


def test_prior_unrelated_unit_not_relevant():
    from sentinel.systemd_production_target_policy import (
        ACTION_RESTART,
        SystemdAttemptFact,
    )
    attempts = [
        SystemdAttemptFact(
            unit="other-service.service",
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 900,
        )
    ]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is True
    assert result.reason == ELIGIBLE


def test_prior_unrelated_action_not_relevant():
    from sentinel.systemd_production_target_policy import SystemdAttemptFact
    attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action="stop",
            timestamp=_now().timestamp() - 900,
        )
    ]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is True
    assert result.reason == ELIGIBLE


def test_malformed_attempt_evidence_fails_closed():
    attempts = ["not-an-attempt-fact"]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is False
    assert "malformed" in result.reason


# --- Identity validation ---


def test_wrong_decision_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "decision_id", "wrong")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_decision" in result.reason


def test_wrong_scope_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "approved_scope_id", "wrong")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_approved_scope" in result.reason


def test_wrong_slo_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "slo_definition_id", "wrong")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_slo" in result.reason


def test_wrong_source_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "measurement_source_id", "wrong")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_measurement_source" in result.reason


def test_wrong_component_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "component_id", "wrong")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_component" in result.reason


def test_wrong_unit_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "target", "wrong.service")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_unit" in result.reason


def test_wrong_action_denied():
    candidate = _valid_candidate()
    object.__setattr__(candidate, "consequence", "stop")
    result = classify_slo_admission(candidate, now=_now())
    assert result.eligible is False
    assert "wrong_action" in result.reason


# --- No caller-supplied outcome ---


def test_no_previous_outcome_parameter():
    """The public API must not accept previous_outcome."""
    with pytest.raises(TypeError):
        classify_slo_admission(
            _valid_candidate(), now=_now(), previous_outcome="EXECUTION_FAILED"
        )


def test_no_cooldown_calculation():
    """Stage 2 must not calculate cooldown. Prior attempt → evidence unavailable, not cooldown_active."""
    from sentinel.systemd_production_target_policy import (
        ACTION_RESTART,
        SystemdAttemptFact,
    )
    attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 1,  # 1 second ago
        )
    ]
    result = classify_slo_admission(_valid_candidate(), now=_now(), attempts=attempts)
    assert result.eligible is False
    # Must be evidence unavailable, NOT cooldown
    assert "evidence" in result.reason
    assert "cooldown" not in result.reason


def test_no_elapsed_time_decision():
    """Elapsed time must not influence the decision. Any prior attempt → same result."""
    from sentinel.systemd_production_target_policy import (
        ACTION_RESTART,
        SystemdAttemptFact,
    )
    # Very old attempt
    old_attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 100000,
        )
    ]
    result_old = classify_slo_admission(_valid_candidate(), now=_now(), attempts=old_attempts)

    # Recent attempt
    recent_attempts = [
        SystemdAttemptFact(
            unit=UNIT,
            action=ACTION_RESTART,
            timestamp=_now().timestamp() - 1,
        )
    ]
    result_recent = classify_slo_admission(_valid_candidate(), now=_now(), attempts=recent_attempts)

    # Both must produce the same result (evidence unavailable)
    assert result_old.eligible == result_recent.eligible == False
    assert result_old.reason == result_recent.reason


# --- Production safety ---


def test_no_tmux_identity():
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert "tmux" not in result.unit.lower()


def test_no_pane_id():
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert "pane" not in result.unit.lower()
    assert "service" in result.unit


def test_result_is_immutable():
    result = classify_slo_admission(_valid_candidate(), now=_now())
    with pytest.raises(AttributeError):
        result.eligible = False


def test_identity_continuity():
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert result.decision_id == DECISION_ID
    assert result.approved_scope_id == APPROVED_SCOPE_ID
    assert result.slo_definition_id == SLO_DEFINITION_ID
    assert result.measurement_source_id == MEASUREMENT_SOURCE_ID
    assert result.component_id == COMPONENT_ID
    assert result.unit == UNIT
    assert result.action == ACTION


def test_systemd_native_target():
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert result.unit == "airiv-sentinel.service"
    assert "tmux" not in result.unit.lower()
    assert "pane" not in result.unit.lower()


def test_no_incident_created():
    """Stage 2 must not import or construct any incident type."""
    import sentinel.slo_systemd_admission_eligibility as mod
    assert not hasattr(mod, "Incident")
    assert not hasattr(mod, "IncidentManager")


def test_no_commander_authorization_created():
    """Stage 2 must not construct Commander authorization objects."""
    import sentinel.slo_systemd_admission_eligibility as mod
    assert not hasattr(mod, "SystemdProductionCommanderAuthorizationContext")


def test_no_activation_created():
    """Stage 2 must not construct activation grants."""
    import sentinel.slo_systemd_admission_eligibility as mod
    assert not hasattr(mod, "SystemdProductionActivationGrant")


def test_no_execution_id_created():
    """Stage 2 must not generate execution_id values."""
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert not hasattr(result, "execution_id")


def test_no_permit_id_created():
    """Stage 2 must not generate permit_id values."""
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert not hasattr(result, "permit_id")


def test_no_bound_systemd_plan_created():
    """Stage 2 must not construct BoundSystemdPlan objects."""
    import sentinel.slo_systemd_admission_eligibility as mod
    assert not hasattr(mod, "BoundSystemdPlan")


def test_no_command_execution():
    """Stage 2 must not import subprocess or reference systemctl."""
    import sentinel.slo_systemd_admission_eligibility as mod
    import inspect
    source = inspect.getsource(mod)
    # Check imports only (docstring may mention systemctl in "does NOT" list)
    for line in source.splitlines():
        if line.strip().startswith("import ") or line.strip().startswith("from "):
            assert "subprocess" not in line
            assert "systemctl" not in line


def test_cooldown_seconds_metadata_preserved():
    """Authority cooldown value is preserved as metadata, not enforced."""
    result = classify_slo_admission(_valid_candidate(), now=_now())
    assert result.cooldown_seconds == 1800.0
