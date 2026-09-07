from sentinel.incidents.manager import IncidentManager
from sentinel.integration.bridge import SentinelIntegrationBridge
from sentinel.runtime_sensor_adapter import RuntimeSensorAdapter


def test_multiple_contract_violations_emit_one_incident():
    manager = IncidentManager()
    bridge = SentinelIntegrationBridge(incident_manager=manager)
    adapter = RuntimeSensorAdapter(bridge=bridge)

    observation = {
        "source": "tmux",
        # Intentionally missing captured_at.
        "pane_id": "%decision-b",
        "session_name": "airiv",
        "window_name": "audit",
        "pane_title": "audit",
        "agent_identity": "SYNTHETIC",
        "pane_dead": True,
        "capture_ok": True,
        "active": False,
        "current_command": "bash",
        "previous_command": "bash",
        "pid": 999995,
        "output_length": 0,
        "output_hash": "",
        "output_changed": False,
        "first_observation": True,
    }

    incidents = adapter.process_tick([observation])

    # Decision B:
    # one lifecycle Incident emitted for this component/tick.
    assert len(incidents) == 1

    incident = incidents[0]

    assert incident.incident_id
    assert incident.component_id == "%decision-b"
    assert incident.status == "OPEN"

    # Both independent violations remain preserved as evidence.
    assert incident.evidence_store.count() == 2

    records = incident.evidence_store.records()

    assert len(records) == 2

    assert all(
        record.evidence_type == "CONTRACT_VIOLATION"
        for record in records
    )

    reasons = {record.reason for record in records}

    assert any(
        "captured_at" in reason
        for reason in reasons
    )

    assert any(
        "pane" in reason.lower()
        and "dead" in reason.lower()
        for reason in reasons
    )

    # IncidentManager still owns the canonical active Incident.
    assert manager.get_active_incident("%decision-b") is incident


def test_same_incident_is_not_emitted_twice_for_multiple_violations():
    manager = IncidentManager()
    bridge = SentinelIntegrationBridge(incident_manager=manager)
    adapter = RuntimeSensorAdapter(bridge=bridge)

    observation = {
        "source": "tmux",
        "pane_id": "%decision-b-identity",
        "session_name": "airiv",
        "window_name": "audit",
        "pane_title": "audit",
        "agent_identity": "SYNTHETIC",
        "pane_dead": True,
        "capture_ok": True,
        "active": False,
        "current_command": "bash",
        "previous_command": "bash",
        "pid": 999996,
        "output_length": 0,
        "output_hash": "",
        "output_changed": False,
        "first_observation": True,
    }

    incidents = adapter.process_tick([observation])

    assert len(incidents) == 1
    assert incidents[0] is manager.get_active_incident("%decision-b-identity")
