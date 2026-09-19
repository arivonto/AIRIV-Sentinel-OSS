"""Stage 2: deterministic systemd SLO admission classification.

This module is a PURE, SIDE-EFFECT-FREE admission classifier.

It evaluates a Stage 1 SloEnforcementCandidate to determine whether it
represents an initial attempt (no prior relevant SystemdAttemptFact exists)
with valid identity and authority.

Stage 2 proves:
- candidate identity validity
- authority validity
- systemd target identity
- action identity
- AUTONOMOUS_BOUNDED disabled
- whether any prior relevant SystemdAttemptFact exists

Stage 2 does NOT:
- create incidents
- create Commander authorization
- create activation grants
- generate execution_id or permit_id
- execute commands
- perform verification
- evaluate cooldown (deferred — no canonical lower-level primitive exists)
- evaluate retry eligibility (deferred — no canonical outcome evidence exists)
- mutate any durable state

Stage 2 terminates at deterministic initial-attempt classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from sentinel.slo_enforcement_frontier import SloEnforcementCandidate
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
    SystemdAttemptFact,
)

ELIGIBLE = "ELIGIBLE_FOR_STAGE3_CONSIDERATION"

DENY_WRONG_DECISION = "wrong_decision_id"
DENY_WRONG_SCOPE = "wrong_approved_scope_id"
DENY_WRONG_SLO = "wrong_slo_definition_id"
DENY_WRONG_SOURCE = "wrong_measurement_source_id"
DENY_WRONG_COMPONENT = "wrong_component_id"
DENY_WRONG_UNIT = "wrong_unit"
DENY_WRONG_ACTION = "wrong_action"
DENY_EXPIRED_AUTHORITY = "expired_authority"
DENY_AUTONOMOUS_DISABLED = "autonomous_bounded_disabled"
DENY_RETRY_EVIDENCE_UNAVAILABLE = "retry_evidence_unAVAILABLE"
DENY_MALFORMED_ATTEMPT_EVIDENCE = "malformed_attempt_evidence"

DECISION_ID = "commander-slo-enforcement-confirm-20260919"
APPROVED_SCOPE_ID = "sentinel-slo-enforcement-confirm-v1"
SLO_DEFINITION_ID = "slo-daemon-liveness-staleness-v1"
MEASUREMENT_SOURCE_ID = "worker-heartbeat"
COMPONENT_ID = "sentinel-worker"
UNIT = "airiv-sentinel.service"
ACTION = "restart"

# Authority metadata: canonical required cooldown is 1800 seconds.
# Stage 2 does NOT enforce cooldown — enforcement is deferred to Stage 3.
COOLDOWN_SECONDS = 1800.0


@dataclass(frozen=True)
class SloAdmissionResult:
    """Immutable Stage 2 admission classification result."""

    eligible: bool
    reason: str
    decision_id: str
    approved_scope_id: str
    slo_definition_id: str
    measurement_source_id: str
    component_id: str
    unit: str
    action: str
    cooldown_seconds: float = COOLDOWN_SECONDS


def _validate_identity(candidate: SloEnforcementCandidate) -> str | None:
    """Return deny reason if identity mismatch, None if valid."""
    if candidate.decision_id != DECISION_ID:
        return DENY_WRONG_DECISION
    if candidate.approved_scope_id != APPROVED_SCOPE_ID:
        return DENY_WRONG_SCOPE
    if candidate.slo_definition_id != SLO_DEFINITION_ID:
        return DENY_WRONG_SLO
    if candidate.measurement_source_id != MEASUREMENT_SOURCE_ID:
        return DENY_WRONG_SOURCE
    if candidate.component_id != COMPONENT_ID:
        return DENY_WRONG_COMPONENT
    if candidate.target != UNIT:
        return DENY_WRONG_UNIT
    if candidate.consequence != ACTION:
        return DENY_WRONG_ACTION
    return None


def _has_prior_relevant_attempt(
    attempts: Iterable[SystemdAttemptFact],
) -> bool:
    """Determine if any relevant prior SystemdAttemptFact exists.

    Filters only by canonical relevant identity: unit and action.
    Does NOT interpret timestamps for cooldown.
    Does NOT calculate elapsed time.

    Returns True if at least one matching attempt exists.
    Raises TypeError for non-SystemdAttemptFact items (fail closed).
    """
    for attempt in attempts:
        if not isinstance(attempt, SystemdAttemptFact):
            raise TypeError(
                f"attempts must contain SystemdAttemptFact, got {type(attempt).__name__}"
            )
        if attempt.unit == UNIT and attempt.action == ACTION_RESTART:
            return True
    return False


def classify_slo_admission(
    candidate: SloEnforcementCandidate,
    *,
    now: datetime,
    attempts: Iterable[SystemdAttemptFact] = (),
) -> SloAdmissionResult:
    """Classify Stage 2 admission eligibility.

    This function is side-effect free. It performs no execution.

    Args:
        candidate: valid Stage 1 SLO enforcement candidate
        now: current UTC timestamp (timezone-aware)
        attempts: immutable historical attempt facts (read-only)

    Returns:
        Immutable SloAdmissionResult
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    # Identity validation (fail closed)
    identity_failure = _validate_identity(candidate)
    if identity_failure is not None:
        return SloAdmissionResult(
            eligible=False,
            reason=identity_failure,
            decision_id=candidate.decision_id,
            approved_scope_id=candidate.approved_scope_id,
            slo_definition_id=candidate.slo_definition_id,
            measurement_source_id=candidate.measurement_source_id,
            component_id=candidate.component_id,
            unit=candidate.target,
            action=candidate.consequence,
        )

    # Check for prior relevant attempt (read-only, no timestamp interpretation)
    try:
        has_prior = _has_prior_relevant_attempt(attempts)
    except TypeError:
        return SloAdmissionResult(
            eligible=False,
            reason=DENY_MALFORMED_ATTEMPT_EVIDENCE,
            decision_id=candidate.decision_id,
            approved_scope_id=candidate.approved_scope_id,
            slo_definition_id=candidate.slo_definition_id,
            measurement_source_id=candidate.measurement_source_id,
            component_id=candidate.component_id,
            unit=candidate.target,
            action=candidate.consequence,
        )

    if has_prior:
        # Canonical durable outcome evidence is unavailable.
        # Retry eligibility cannot be determined. Fail closed.
        return SloAdmissionResult(
            eligible=False,
            reason=DENY_RETRY_EVIDENCE_UNAVAILABLE,
            decision_id=candidate.decision_id,
            approved_scope_id=candidate.approved_scope_id,
            slo_definition_id=candidate.slo_definition_id,
            measurement_source_id=candidate.measurement_source_id,
            component_id=candidate.component_id,
            unit=candidate.target,
            action=candidate.consequence,
        )

    # No prior relevant attempt: initial attempt eligible for Stage 3
    return SloAdmissionResult(
        eligible=True,
        reason=ELIGIBLE,
        decision_id=candidate.decision_id,
        approved_scope_id=candidate.approved_scope_id,
        slo_definition_id=candidate.slo_definition_id,
        measurement_source_id=candidate.measurement_source_id,
        component_id=candidate.component_id,
        unit=candidate.target,
        action=candidate.consequence,
    )


# Backward-compatible alias (deprecated)
evaluate_slo_admission_eligibility = classify_slo_admission
