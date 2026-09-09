from dataclasses import FrozenInstanceError

from sentinel.incidents.manager import IncidentManager
from sentinel.observability_metrics import (
    ReconciliationHealth,
    project_incidents,
    project_remediation,
    reconcile_incidents,
)


def observation(component="%1"):
    return {"pane_id": component, "agent_identity": "CHATGPT"}


def test_incident_metrics_are_explicit_and_read_only():
    manager = IncidentManager()
    first = manager.evaluate_anomaly(observation("%1"), "STUCK")
    manager.investigate("%1")
    manager.evaluate_anomaly(observation("%2"), "FAILED")
    manager.resolve("%1", {"verified": True}, final_outcome="RECOVERED")

    projection = project_incidents(manager)
    assert projection.active_total == 1
    assert dict(projection.active_lifecycle_counts) == {
        "OPEN": 1, "INVESTIGATING": 0, "TERMINAL": 0,
    }
    assert projection.history_terminal_total == 1
    assert dict(projection.history_outcome_counts)["RECOVERED"] == 1
    assert projection.unknown_active_lifecycle_counts == ()
    assert projection.unknown_history_outcome_counts == ()
    assert manager.get_active_incident("%2") is not None
    assert first.final_outcome == "RECOVERED"
    try:
        projection.active_total = 9
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("projection must be immutable")


def test_unknown_values_are_preserved_not_coerced():
    manager = IncidentManager()
    incident = manager.evaluate_anomaly(observation(), "STUCK")
    incident.status = "ALIEN"
    incident.lifecycle_state = "ALIEN"
    manager.incident_history.append({
        "incident_id": "H-1", "status": "TERMINAL",
        "lifecycle_state": "TERMINAL", "final_outcome": "MYSTERY",
    })
    projection = project_incidents(manager)
    assert dict(projection.unknown_active_lifecycle_counts) == {"ALIEN": 1}
    assert dict(projection.unknown_history_outcome_counts) == {"MYSTERY": 1}


def test_remediation_projection_counts_only_explicit_labels():
    records = [
        {"status": "SUCCEEDED"},
        {"outcome": "FAILED"},
        {"status": "succeeded"},
        {},
    ]
    projection = project_remediation(records)
    assert projection.total == 4
    assert dict(projection.status_counts) == {"FAILED": 1, "SUCCEEDED": 2}
    assert projection.missing_status == 1


def test_reconciliation_reports_health_without_mutation():
    manager = IncidentManager()
    active = manager.evaluate_anomaly(observation("%1"), "STUCK")
    manager.incident_history.extend([
        {"incident_id": "H-1", "status": "INVESTIGATING",
         "lifecycle_state": "INVESTIGATING", "final_outcome": None},
        {"incident_id": active.incident_id, "status": "TERMINAL",
         "lifecycle_state": "TERMINAL", "final_outcome": "RECOVERED"},
    ])
    result = reconcile_incidents(manager)
    assert result.health is ReconciliationHealth.DEGRADED
    assert result.nonterminal_history_incidents == ("H-1",)
    assert result.missing_history_outcomes == ("H-1",)
    assert result.duplicate_incident_ids == (active.incident_id,)
    assert manager.get_active_incident("%1") is active
    assert active.status == "OPEN"


def test_clean_reconciliation_is_healthy():
    manager = IncidentManager()
    manager.evaluate_anomaly(observation(), "STUCK")
    manager.resolve("%1", {"verified": True}, final_outcome="RECOVERED")
    result = reconcile_incidents(manager)
    assert result.health is ReconciliationHealth.HEALTHY
    assert result.active_terminal_incidents == ()
    assert result.nonterminal_history_incidents == ()
    assert result.missing_history_outcomes == ()
    assert result.duplicate_incident_ids == ()
