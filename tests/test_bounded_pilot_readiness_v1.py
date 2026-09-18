"""Bounded pilot readiness gate regression."""

import pytest

from sentinel.bounded_pilot_readiness import (
    PILOT_ACTION,
    PILOT_AUTHORITY_TTL_SECONDS,
    PILOT_HELPER_ID,
    PILOT_HELPER_SUBJECT,
    PILOT_UNIT,
    BoundedPilotApproval,
    BoundedPilotHelperFacts,
    BoundedPilotReadinessState,
    BoundedPilotRuntimeFacts,
    BoundedPilotVerificationFacts,
    assess_bounded_pilot_readiness,
)


def approval(**changes):
    return BoundedPilotApproval(**changes)


def helper(**changes):
    values = dict(
        helper_id=PILOT_HELPER_ID,
        unit=PILOT_UNIT,
        action=PILOT_ACTION,
        subject_system_unit=PILOT_HELPER_SUBJECT,
        accepts_only_exact_unit=True,
        accepts_only_restart=True,
        no_shell=True,
        no_provider_calls=True,
        no_external_delivery=True,
        polkit_rule_present=True,
        helper_installed=True,
    )
    values.update(changes)
    return BoundedPilotHelperFacts(**values)


def verification(**changes):
    values = dict(
        pid_check=True,
        active_state_check=True,
        runtime_identity_check=True,
        journal_continuity_check=True,
        evidence_path_validated=True,
    )
    values.update(changes)
    return BoundedPilotVerificationFacts(**values)


def runtime(**changes):
    values = dict(
        now=1000.0,
        activated_at=999.0,
        unknown_retry_count=0,
        active_effects=0,
    )
    values.update(changes)
    return BoundedPilotRuntimeFacts(**values)


def assess(**changes):
    values = dict(
        approval=approval(),
        helper=helper(),
        verification=verification(),
        runtime=runtime(),
    )
    values.update(changes)
    return assess_bounded_pilot_readiness(**values)


def test_exact_approved_pilot_is_ready():
    result = assess()

    assert result.ready is True
    assert result.state is BoundedPilotReadinessState.READY
    assert result.reasons == ("bounded_pilot_ready",)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("helper_id", "other", "helper_identity_mismatch"),
        ("unit", "other.service", "helper_unit_mismatch"),
        ("action", "STOP", "helper_action_mismatch"),
        ("subject_system_unit", "other.service", "helper_subject_mismatch"),
        ("accepts_only_exact_unit", False, "helper_accepts_broad_unit"),
        ("accepts_only_restart", False, "helper_accepts_non_restart"),
        ("no_shell", False, "helper_shell_allowed"),
        ("no_provider_calls", False, "helper_provider_calls_allowed"),
        ("no_external_delivery", False, "helper_external_delivery_allowed"),
        ("polkit_rule_present", False, "polkit_rule_missing"),
        ("helper_installed", False, "helper_not_installed"),
    ],
)
def test_helper_mismatch_blocks_activation(field, value, reason):
    result = assess(helper=helper(**{field: value}))

    assert result.ready is False
    assert result.state is BoundedPilotReadinessState.ACTIVATION_BLOCKED
    assert reason in result.reasons


@pytest.mark.parametrize(
    "field,reason",
    [
        ("pid_check", "pid_verification_missing"),
        ("active_state_check", "active_state_verification_missing"),
        ("runtime_identity_check", "runtime_identity_verification_missing"),
        ("journal_continuity_check", "journal_continuity_verification_missing"),
        ("evidence_path_validated", "evidence_path_not_validated"),
    ],
)
def test_verification_gap_blocks_activation(field, reason):
    result = assess(verification=verification(**{field: False}))

    assert result.ready is False
    assert reason in result.reasons


def test_unknown_outcome_never_gets_retry_budget():
    result = assess(runtime=runtime(unknown_retry_count=1))

    assert result.ready is False
    assert "unknown_retry_budget_exceeded" in result.reasons


def test_single_service_blast_radius_blocks_second_active_effect():
    result = assess(runtime=runtime(active_effects=1))

    assert result.ready is False
    assert "blast_radius_unavailable" in result.reasons


def test_authority_expires_after_seven_days():
    result = assess(
        runtime=runtime(
            now=PILOT_AUTHORITY_TTL_SECONDS + 1000.0,
            activated_at=999.0,
        )
    )

    assert result.ready is False
    assert "activation_expired" in result.reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "other.service"},
        {"action": "STOP"},
        {"max_unknown_retries": 1},
        {"max_active_effects": 2},
        {"local_journal_only": False},
        {"manual_rollback_only": False},
    ],
)
def test_approval_envelope_is_not_mutable(changes):
    with pytest.raises(ValueError):
        approval(**changes)
