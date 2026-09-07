from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from sentinel.diagnostic.models import (
    DiagnosticActionState,
    InvestigationState,
)
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticConfig,
    RuntimeDiagnosticCoordinator,
)
from sentinel.incidents.manager import Incident


def make_incident(
    incident_id: str = "INC-RUNTIME-001",
    component_id: str = "%0",
    anomaly_type: str = "TMUX_PANE_FAILURE",
) -> Incident:
    return Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="sentinel-runtime",
        anomaly_type=anomaly_type,
    )


def make_coordinator(tmp_path: Path, monkeypatch) -> RuntimeDiagnosticCoordinator:
    diagnostic_root = tmp_path / "diagnostic"

    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(diagnostic_root),
    )

    config = RuntimeDiagnosticConfig(
        max_duration_seconds=60.0,
        max_actions=5,
        max_repeated_action=2,
        max_risk=5,
        minimum_evidence=1,
        cycle_interval_seconds=0.01,
    )

    return RuntimeDiagnosticCoordinator(config=config)


def test_runtime_incident_creates_single_investigation(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incident = make_incident()

    investigation = coordinator.register_incident(incident)

    assert investigation is not None
    assert investigation.incident_id == incident.incident_id
    assert investigation.component_id == incident.component_id
    assert investigation.state is InvestigationState.ACTIVE

    persisted = coordinator.engine.get(
        investigation.investigation_id
    )

    assert persisted is not None
    assert persisted.incident_id == incident.incident_id


def test_duplicate_incident_reuses_existing_investigation(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incident = make_incident()

    first = coordinator.register_incident(incident)
    second = coordinator.register_incident(incident)

    assert first.investigation_id == second.investigation_id
    assert len(coordinator._investigation_by_incident) == 1


def test_submit_accepts_runtime_incident_batch(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incidents = [
        make_incident("INC-RUNTIME-001", "%0"),
        make_incident("INC-RUNTIME-002", "%1"),
    ]

    coordinator.submit(incidents)

    assert len(coordinator._investigation_by_incident) == 2


def test_one_cycle_processes_one_step(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incident = make_incident()
    investigation = coordinator.register_incident(incident)

    calls = []

    original_execute = coordinator.executor.execute

    def execute(action):
        calls.append(action)
        return original_execute(action)

    monkeypatch.setattr(
        coordinator.executor,
        "execute",
        execute,
    )

    results = coordinator.run_cycle()

    assert len(results) == 1
    assert len(calls) == 1

    action = calls[0]

    assert action.investigation_id == investigation.investigation_id
    assert action.incident_id == incident.incident_id
    assert "{component_id}" not in action.command
    assert incident.component_id in action.command


def test_completed_diagnostic_action_is_persisted(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incident = make_incident()
    investigation = coordinator.register_incident(incident)

    results = coordinator.run_cycle()

    assert len(results) == 1

    result = results[0]

    assert result.investigation.investigation_id == (
        investigation.investigation_id
    )
    assert result.action is not None

    action = coordinator.investigation_manager.store.get_action(
        investigation.investigation_id,
        result.action.diagnostic_action_id,
    )

    assert action is not None
    assert action.state is DiagnosticActionState.COMPLETED
    assert action.result is not None


def test_runtime_coordinator_has_no_remediation_entrypoint():
    assert not hasattr(
        RuntimeDiagnosticCoordinator,
        "remediate",
    )


def test_runtime_coordinator_does_not_own_incident_manager():
    coordinator = object.__new__(RuntimeDiagnosticCoordinator)

    assert not hasattr(
        coordinator,
        "incident_manager",
    )


def test_recovery_delegates_to_engine(tmp_path, monkeypatch):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    calls = []

    def recover():
        calls.append("engine.recover")
        return []

    monkeypatch.setattr(
        coordinator.engine,
        "recover",
        recover,
    )

    coordinator.recover()

    assert calls == ["engine.recover"]


def test_terminal_investigation_is_not_processed_again(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    incident = make_incident()
    investigation = coordinator.register_incident(incident)

    assert investigation is not None

    investigation.state = InvestigationState.COMPLETED
    coordinator.investigation_manager.store.save_investigation(
        investigation
    )

    calls = []

    def execute(action):
        calls.append(action)
        raise AssertionError(
            "terminal investigation must not execute"
        )

    monkeypatch.setattr(
        coordinator.executor,
        "execute",
        execute,
    )

    results = coordinator.run_cycle()

    assert results == []
    assert calls == []
