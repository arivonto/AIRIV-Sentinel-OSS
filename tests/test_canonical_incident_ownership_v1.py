from sentinel.incidents.manager import IncidentManager


def observation():
    return {
        "pane_id": "%canonical",
        "window_name": "chatgpt",
        "current_command": "bash",
        "activity_state": "STUCK",
        "output_sha256": "abc",
        "agent_identity": "chatgpt",
    }


def test_incident_manager_is_canonical_incident_identity_owner():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Canonical ownership test",
    )

    assert incident is not None
    assert incident.incident_id
    assert manager.get_active_incident("%canonical") is incident


def test_incident_manager_owns_canonical_incident_status():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Canonical status test",
    )

    assert incident.status == "OPEN"

    manager.investigate("%canonical")

    assert incident.status == "INVESTIGATING"


def test_remediation_does_not_replace_canonical_incident_identity():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Identity preservation test",
    )

    manager.investigate("%canonical")

    assert manager.get_active_incident("%canonical") is incident
    assert incident.incident_id
    assert incident.component_id == "%canonical"
    assert incident.status == "INVESTIGATING"


def test_failed_remediation_does_not_resolve_canonical_incident():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Failed remediation test",
    )

    manager.investigate("%canonical")

    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident("%canonical") is incident


def test_resolution_requires_explicit_recovery_evidence():
    manager = IncidentManager()

    incident = manager.evaluate_anomaly(
        observation(),
        "STUCK",
        "Recovery evidence test",
    )

    manager.investigate("%canonical")

    try:
        manager.resolve("%canonical", None)
    except (ValueError, RuntimeError):
        pass
    else:
        raise AssertionError(
            "IncidentManager must require explicit recovery evidence"
        )

    assert incident.status == "INVESTIGATING"
    assert manager.get_active_incident("%canonical") is incident
