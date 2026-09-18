"""Bounded production pilot readiness gate.

This module is intentionally side-effect free. It records the exact
Commander-approved pilot envelope and decides whether the separately installed
helper and evidence facts are ready for activation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


PILOT_UNIT = "airiv-sentinel.service"
PILOT_ACTION = "RESTART"
PILOT_HELPER_ID = "airiv-sentinel-bounded-restart-helper"
PILOT_HELPER_SUBJECT = "airiv-sentinel.service"
PILOT_COOLDOWN_SECONDS = 1800.0
PILOT_AUTHORITY_TTL_SECONDS = 7 * 24 * 60 * 60
PILOT_MAX_UNKNOWN_RETRIES = 0
PILOT_MAX_ACTIVE_EFFECTS = 1


class BoundedPilotReadinessState(str, Enum):
    READY = "READY"
    ACTIVATION_BLOCKED = "ACTIVATION_BLOCKED"


@dataclass(frozen=True, slots=True)
class BoundedPilotApproval:
    """Exact approval envelope captured from the Commander decision."""

    unit: str = PILOT_UNIT
    action: str = PILOT_ACTION
    cooldown_seconds: float = PILOT_COOLDOWN_SECONDS
    authority_ttl_seconds: float = PILOT_AUTHORITY_TTL_SECONDS
    max_unknown_retries: int = PILOT_MAX_UNKNOWN_RETRIES
    max_active_effects: int = PILOT_MAX_ACTIVE_EFFECTS
    local_journal_only: bool = True
    manual_rollback_only: bool = True

    def __post_init__(self) -> None:
        if self.unit != PILOT_UNIT:
            raise ValueError("bounded_pilot_exact_unit_required")
        if self.action != PILOT_ACTION:
            raise ValueError("bounded_pilot_exact_action_required")
        _positive(self.cooldown_seconds, "cooldown_seconds")
        _positive(self.authority_ttl_seconds, "authority_ttl_seconds")
        if self.max_unknown_retries != PILOT_MAX_UNKNOWN_RETRIES:
            raise ValueError("bounded_pilot_unknown_retry_must_be_zero")
        if self.max_active_effects != PILOT_MAX_ACTIVE_EFFECTS:
            raise ValueError("bounded_pilot_single_effect_required")
        if self.local_journal_only is not True:
            raise ValueError("bounded_pilot_local_journal_required")
        if self.manual_rollback_only is not True:
            raise ValueError("bounded_pilot_manual_rollback_required")


@dataclass(frozen=True, slots=True)
class BoundedPilotHelperFacts:
    helper_id: str
    unit: str
    action: str
    subject_system_unit: str
    accepts_only_exact_unit: bool
    accepts_only_restart: bool
    no_shell: bool
    no_provider_calls: bool
    no_external_delivery: bool
    polkit_rule_present: bool
    helper_installed: bool


@dataclass(frozen=True, slots=True)
class BoundedPilotVerificationFacts:
    pid_check: bool
    active_state_check: bool
    runtime_identity_check: bool
    journal_continuity_check: bool
    evidence_path_validated: bool


@dataclass(frozen=True, slots=True)
class BoundedPilotRuntimeFacts:
    now: float
    activated_at: float | None = None
    unknown_retry_count: int = 0
    active_effects: int = 0


@dataclass(frozen=True, slots=True)
class BoundedPilotReadinessAssessment:
    state: BoundedPilotReadinessState
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.state is BoundedPilotReadinessState.READY


def assess_bounded_pilot_readiness(
    *,
    approval: BoundedPilotApproval,
    helper: BoundedPilotHelperFacts,
    verification: BoundedPilotVerificationFacts,
    runtime: BoundedPilotRuntimeFacts,
) -> BoundedPilotReadinessAssessment:
    """Return READY only when every activation fact is exact and fresh."""

    if type(approval) is not BoundedPilotApproval:
        raise TypeError("BoundedPilotApproval required")
    if type(helper) is not BoundedPilotHelperFacts:
        raise TypeError("BoundedPilotHelperFacts required")
    if type(verification) is not BoundedPilotVerificationFacts:
        raise TypeError("BoundedPilotVerificationFacts required")
    if type(runtime) is not BoundedPilotRuntimeFacts:
        raise TypeError("BoundedPilotRuntimeFacts required")

    _non_negative(runtime.now, "now")
    reasons: list[str] = []

    if helper.helper_id != PILOT_HELPER_ID:
        reasons.append("helper_identity_mismatch")
    if helper.unit != approval.unit:
        reasons.append("helper_unit_mismatch")
    if helper.action != approval.action:
        reasons.append("helper_action_mismatch")
    if helper.subject_system_unit != PILOT_HELPER_SUBJECT:
        reasons.append("helper_subject_mismatch")

    helper_boolean_requirements = {
        "helper_not_installed": helper.helper_installed,
        "polkit_rule_missing": helper.polkit_rule_present,
        "helper_accepts_broad_unit": helper.accepts_only_exact_unit,
        "helper_accepts_non_restart": helper.accepts_only_restart,
        "helper_shell_allowed": helper.no_shell,
        "helper_provider_calls_allowed": helper.no_provider_calls,
        "helper_external_delivery_allowed": helper.no_external_delivery,
    }
    for reason, satisfied in helper_boolean_requirements.items():
        if satisfied is not True:
            reasons.append(reason)

    verification_requirements = {
        "pid_verification_missing": verification.pid_check,
        "active_state_verification_missing": verification.active_state_check,
        "runtime_identity_verification_missing": (
            verification.runtime_identity_check
        ),
        "journal_continuity_verification_missing": (
            verification.journal_continuity_check
        ),
        "evidence_path_not_validated": verification.evidence_path_validated,
    }
    for reason, satisfied in verification_requirements.items():
        if satisfied is not True:
            reasons.append(reason)

    if runtime.unknown_retry_count != 0:
        reasons.append("unknown_retry_budget_exceeded")
    if runtime.active_effects not in (0, 1):
        reasons.append("active_effect_count_invalid")
    if runtime.active_effects >= approval.max_active_effects:
        reasons.append("blast_radius_unavailable")

    if runtime.activated_at is None:
        reasons.append("activation_not_recorded")
    else:
        _non_negative(runtime.activated_at, "activated_at")
        if runtime.activated_at > runtime.now:
            reasons.append("activation_from_future")
        elif runtime.now >= (
            runtime.activated_at + approval.authority_ttl_seconds
        ):
            reasons.append("activation_expired")

    if reasons:
        return BoundedPilotReadinessAssessment(
            state=BoundedPilotReadinessState.ACTIVATION_BLOCKED,
            reasons=tuple(reasons),
        )

    return BoundedPilotReadinessAssessment(
        state=BoundedPilotReadinessState.READY,
        reasons=("bounded_pilot_ready",),
    )


def _positive(value: float, name: str) -> float:
    current = _finite_number(value, name)
    if current <= 0:
        raise ValueError(f"{name} must be positive")
    return current


def _non_negative(value: float, name: str) -> float:
    current = _finite_number(value, name)
    if current < 0:
        raise ValueError(f"{name} must be non-negative")
    return current


def _finite_number(value: float, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return float(value)
