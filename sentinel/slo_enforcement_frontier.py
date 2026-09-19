"""SLO enforcement frontier: deterministic breach evaluation and candidate preparation.

This module is a pure front-end. It performs NO execution.

It evaluates caller-supplied WorkerHealthStatus evidence against a single
canonical SLO definition and, when a breach is determinate, prepares a
proposed restart candidate for explicit Commander confirmation through the
existing RemediationPolicy interface.

Authority: docs/AIRIV_SENTINEL_SLO_ENFORCEMENT_DECISION_RECORD_V1.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sentinel.worker.health import WorkerHealthStatus

if TYPE_CHECKING:
    from sentinel.remediation_policy import RemediationRequest

SLO_DAEMON_LIVENESS_STALENESS_V1 = "slo-daemon-liveness-staleness-v1"
MEASUREMENT_SOURCE_WORKER_HEARTBEAT = "worker-heartbeat"
COMPONENT_SENTINEL_WORKER = "sentinel-worker"
TARGET_AIRIV_SENTINEL_SERVICE = "airiv-sentinel.service"
CONSEQUENCE_RESTART = "restart"

ENFORCEMENT_MODE_COMMANDER_CONFIRM = "COMMANDER_CONFIRM"
ENFORCEMENT_MODE_AUTONOMOUS_BOUNDED = "AUTONOMOUS_BOUNDED"


class SloEnforcementError(Exception):
    """Base exception for SLO enforcement frontier."""


class SloEnforcementExpiredError(SloEnforcementError):
    """Raised when the authority record has expired."""


class SloEnforcementDeniedError(SloEnforcementError):
    """Raised when the enforcement candidate is denied."""


class SloEnforcementAutonomousDisabledError(SloEnforcementError):
    """Raised when AUTONOMOUS_BOUNDED mode is requested."""


@dataclass(frozen=True)
class SloEnforcementCandidate:
    """Immutable proposed restart candidate prepared for Commander confirmation.

    This object performs no execution. It binds sufficient identity for the
    existing RemediationPolicy to evaluate the proposed effect.
    """

    decision_id: str
    approved_scope_id: str
    slo_definition_id: str
    measurement_source_id: str
    component_id: str
    target: str
    consequence: str
    worker_id: str
    observed_at: datetime
    age_seconds: float | None

    def to_remediation_request(self, incident_state: str) -> RemediationRequest:
        """Adapt this candidate to the canonical RemediationRequest interface."""
        from sentinel.remediation_policy import RemediationRequest

        return RemediationRequest(
            incident_state=incident_state,
            component_id=self.component_id,
            action=self.consequence,
        )


def evaluate_slo_breach(
    *,
    status: WorkerHealthStatus,
    slo_definition_id: str,
    measurement_source_id: str,
    component_id: str,
    target: str,
    worker_id: str,
    observed_at: datetime,
    age_seconds: float | None,
) -> SloEnforcementCandidate:
    """Evaluate deterministic SLO breach evidence and prepare a restart candidate.

    This function is side-effect free. It returns a candidate or raises a
    fail-closed exception. It performs no execution.

    Fail-closed conditions:
    - status is UNKNOWN → denied
    - status is HEALTHY → denied
    - status is UNHEALTHY → denied (not equivalent to STALE)
    - status is not STALE → denied
    - slo_definition_id mismatch → denied
    - measurement_source_id mismatch → denied
    - component_id mismatch → denied
    - target mismatch → denied
    - observed_at is not timezone-aware → denied
    """
    if not isinstance(status, WorkerHealthStatus):
        raise SloEnforcementDeniedError("canonical WorkerHealthStatus required")

    if status == WorkerHealthStatus.UNKNOWN:
        raise SloEnforcementDeniedError("UNKNOWN evidence cannot produce enforcement")

    if status == WorkerHealthStatus.HEALTHY:
        raise SloEnforcementDeniedError("HEALTHY status is not a breach")

    if status == WorkerHealthStatus.UNHEALTHY:
        raise SloEnforcementDeniedError(
            "UNHEALTHY status is not a STALE breach"
        )

    if status != WorkerHealthStatus.STALE:
        raise SloEnforcementDeniedError("only STALE status is an SLO breach")

    if slo_definition_id != SLO_DAEMON_LIVENESS_STALENESS_V1:
        raise SloEnforcementDeniedError("SLO definition ID mismatch")

    if measurement_source_id != MEASUREMENT_SOURCE_WORKER_HEARTBEAT:
        raise SloEnforcementDeniedError("measurement source ID mismatch")

    if component_id != COMPONENT_SENTINEL_WORKER:
        raise SloEnforcementDeniedError("component ID mismatch")

    if target != TARGET_AIRIV_SENTINEL_SERVICE:
        raise SloEnforcementDeniedError("target mismatch")

    if not isinstance(observed_at, datetime):
        raise SloEnforcementDeniedError("observed_at must be a datetime")

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise SloEnforcementDeniedError("observed_at must be timezone-aware")

    return SloEnforcementCandidate(
        decision_id="",
        approved_scope_id="",
        slo_definition_id=slo_definition_id,
        measurement_source_id=measurement_source_id,
        component_id=component_id,
        target=target,
        consequence=CONSEQUENCE_RESTART,
        worker_id=worker_id,
        observed_at=observed_at,
        age_seconds=age_seconds,
    )


def prepare_slo_enforcement_candidate(
    *,
    status: WorkerHealthStatus,
    worker_id: str,
    observed_at: datetime,
    age_seconds: float | None,
    authority_decided_at: datetime,
    authority_expiration: datetime,
    enforcement_mode: str,
) -> SloEnforcementCandidate:
    """Prepare an SLO enforcement candidate under the canonical authority envelope.

    This is the single entry point for SLO enforcement candidate preparation.

    It enforces:
    - authority not expired
    - COMMANDER_CONFIRM mode only (AUTONOMOUS_BOUNDED rejected)
    - deterministic STALE breach only
    - exact SLO/component/target binding

    This function performs no execution.
    """
    if enforcement_mode == ENFORCEMENT_MODE_AUTONOMOUS_BOUNDED:
        raise SloEnforcementAutonomousDisabledError(
            "AUTONOMOUS_BOUNDED enforcement is DISABLED"
        )

    if enforcement_mode != ENFORCEMENT_MODE_COMMANDER_CONFIRM:
        raise SloEnforcementDeniedError("only COMMANDER_CONFIRM mode is authorized")

    now = datetime.now(timezone.utc)
    if now >= authority_expiration:
        raise SloEnforcementExpiredError("authority has expired")

    candidate = evaluate_slo_breach(
        status=status,
        slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
        measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
        component_id=COMPONENT_SENTINEL_WORKER,
        target=TARGET_AIRIV_SENTINEL_SERVICE,
        worker_id=worker_id,
        observed_at=observed_at,
        age_seconds=age_seconds,
    )

    return SloEnforcementCandidate(
        decision_id="commander-slo-enforcement-confirm-20260919",
        approved_scope_id="sentinel-slo-enforcement-confirm-v1",
        slo_definition_id=candidate.slo_definition_id,
        measurement_source_id=candidate.measurement_source_id,
        component_id=candidate.component_id,
        target=candidate.target,
        consequence=candidate.consequence,
        worker_id=candidate.worker_id,
        observed_at=candidate.observed_at,
        age_seconds=candidate.age_seconds,
    )
