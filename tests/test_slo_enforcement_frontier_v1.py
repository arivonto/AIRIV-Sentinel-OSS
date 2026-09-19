"""Focused tests for the SLO enforcement frontier.

These tests prove the front-end breach determination and candidate preparation
logic without performing any production effect.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sentinel.slo_enforcement_frontier import (
    COMPONENT_SENTINEL_WORKER,
    CONSEQUENCE_RESTART,
    MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
    SLO_DAEMON_LIVENESS_STALENESS_V1,
    TARGET_AIRIV_SENTINEL_SERVICE,
    SloEnforcementAutonomousDisabledError,
    SloEnforcementCandidate,
    SloEnforcementDeniedError,
    SloEnforcementExpiredError,
    evaluate_slo_breach,
    prepare_slo_enforcement_candidate,
)
from sentinel.worker.health import WorkerHealthStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return "worker-test-1"


# --- Breach determination ---


def test_healthy_produces_no_candidate():
    with pytest.raises(SloEnforcementDeniedError, match="HEALTHY"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.HEALTHY,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=5.0,
        )


def test_stale_produces_candidate():
    candidate = evaluate_slo_breach(
        status=WorkerHealthStatus.STALE,
        slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
        measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
        component_id=COMPONENT_SENTINEL_WORKER,
        target=TARGET_AIRIV_SENTINEL_SERVICE,
        worker_id=_worker_id(),
        observed_at=_now(),
        age_seconds=3600.0,
    )
    assert isinstance(candidate, SloEnforcementCandidate)
    assert candidate.consequence == CONSEQUENCE_RESTART
    assert candidate.target == TARGET_AIRIV_SENTINEL_SERVICE
    assert candidate.component_id == COMPONENT_SENTINEL_WORKER


def test_unknown_produces_no_candidate():
    with pytest.raises(SloEnforcementDeniedError, match="UNKNOWN"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.UNKNOWN,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=None,
        )


def test_unhealthy_is_not_stale():
    with pytest.raises(SloEnforcementDeniedError, match="UNHEALTHY"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.UNHEALTHY,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=5.0,
        )


def test_wrong_slo_id_denied():
    with pytest.raises(SloEnforcementDeniedError, match="SLO definition ID"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.STALE,
            slo_definition_id="wrong-slo",
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
        )


def test_wrong_measurement_source_denied():
    with pytest.raises(SloEnforcementDeniedError, match="measurement source"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.STALE,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id="wrong-source",
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
        )


def test_wrong_component_denied():
    with pytest.raises(SloEnforcementDeniedError, match="component ID"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.STALE,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id="wrong-component",
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
        )


def test_wrong_target_denied():
    with pytest.raises(SloEnforcementDeniedError, match="target"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.STALE,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target="wrong-target.service",
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
        )


def test_naive_datetime_denied():
    with pytest.raises(SloEnforcementDeniedError, match="timezone-aware"):
        evaluate_slo_breach(
            status=WorkerHealthStatus.STALE,
            slo_definition_id=SLO_DAEMON_LIVENESS_STALENESS_V1,
            measurement_source_id=MEASUREMENT_SOURCE_WORKER_HEARTBEAT,
            component_id=COMPONENT_SENTINEL_WORKER,
            target=TARGET_AIRIV_SENTINEL_SERVICE,
            worker_id=_worker_id(),
            observed_at=datetime(2026, 9, 19),  # naive
            age_seconds=3600.0,
        )


# --- Authority envelope ---


def test_expired_authority_denied():
    with pytest.raises(SloEnforcementExpiredError):
        prepare_slo_enforcement_candidate(
            status=WorkerHealthStatus.STALE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
            authority_decided_at=_now() - timedelta(days=14),
            authority_expiration=_now() - timedelta(days=7),
            enforcement_mode="COMMANDER_CONFIRM",
        )


def test_autonomous_bounded_rejected():
    with pytest.raises(SloEnforcementAutonomousDisabledError):
        prepare_slo_enforcement_candidate(
            status=WorkerHealthStatus.STALE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
            authority_decided_at=_now(),
            authority_expiration=_now() + timedelta(days=7),
            enforcement_mode="AUTONOMOUS_BOUNDED",
        )


def test_wrong_mode_denied():
    with pytest.raises(SloEnforcementDeniedError, match="COMMANDER_CONFIRM"):
        prepare_slo_enforcement_candidate(
            status=WorkerHealthStatus.STALE,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=3600.0,
            authority_decided_at=_now(),
            authority_expiration=_now() + timedelta(days=7),
            enforcement_mode="REPORT_ONLY",
        )


def test_commander_confirm_stale_produces_candidate():
    candidate = prepare_slo_enforcement_candidate(
        status=WorkerHealthStatus.STALE,
        worker_id=_worker_id(),
        observed_at=_now(),
        age_seconds=3600.0,
        authority_decided_at=_now(),
        authority_expiration=_now() + timedelta(days=7),
        enforcement_mode="COMMANDER_CONFIRM",
    )
    assert candidate.decision_id == "commander-slo-enforcement-confirm-20260919"
    assert candidate.approved_scope_id == "sentinel-slo-enforcement-confirm-v1"
    assert candidate.consequence == CONSEQUENCE_RESTART
    assert candidate.slo_definition_id == SLO_DAEMON_LIVENESS_STALENESS_V1
    assert candidate.measurement_source_id == MEASUREMENT_SOURCE_WORKER_HEARTBEAT
    assert candidate.component_id == COMPONENT_SENTINEL_WORKER
    assert candidate.target == TARGET_AIRIV_SENTINEL_SERVICE


def test_candidate_adapts_to_remediation_request():
    candidate = prepare_slo_enforcement_candidate(
        status=WorkerHealthStatus.STALE,
        worker_id=_worker_id(),
        observed_at=_now(),
        age_seconds=3600.0,
        authority_decided_at=_now(),
        authority_expiration=_now() + timedelta(days=7),
        enforcement_mode="COMMANDER_CONFIRM",
    )
    request = candidate.to_remediation_request(incident_state="active")
    assert request.component_id == COMPONENT_SENTINEL_WORKER
    assert request.action == CONSEQUENCE_RESTART
    assert request.incident_state == "active"


def test_candidate_preparation_performs_no_execution():
    """Candidate preparation must not invoke any execution path."""
    candidate = prepare_slo_enforcement_candidate(
        status=WorkerHealthStatus.STALE,
        worker_id=_worker_id(),
        observed_at=_now(),
        age_seconds=3600.0,
        authority_decided_at=_now(),
        authority_expiration=_now() + timedelta(days=7),
        enforcement_mode="COMMANDER_CONFIRM",
    )
    assert isinstance(candidate, SloEnforcementCandidate)
    # Candidate has no execution method — it is a pure data object
    assert not hasattr(candidate, "execute")
    assert not hasattr(candidate, "run")


def test_healthy_through_authority_envelope_denied():
    with pytest.raises(SloEnforcementDeniedError, match="HEALTHY"):
        prepare_slo_enforcement_candidate(
            status=WorkerHealthStatus.HEALTHY,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=5.0,
            authority_decided_at=_now(),
            authority_expiration=_now() + timedelta(days=7),
            enforcement_mode="COMMANDER_CONFIRM",
        )


def test_unknown_through_authority_envelope_denied():
    with pytest.raises(SloEnforcementDeniedError, match="UNKNOWN"):
        prepare_slo_enforcement_candidate(
            status=WorkerHealthStatus.UNKNOWN,
            worker_id=_worker_id(),
            observed_at=_now(),
            age_seconds=None,
            authority_decided_at=_now(),
            authority_expiration=_now() + timedelta(days=7),
            enforcement_mode="COMMANDER_CONFIRM",
        )
