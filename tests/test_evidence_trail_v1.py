from sentinel.evidence import EvidenceTrail
from sentinel.incidents.manager import IncidentManager


def test_evidence_trail_is_append_only_and_ordered():
    trail = EvidenceTrail()

    first = trail.append(
        incident_id="INC-1",
        component_id="%0",
        evidence_type="CONTRACT_VIOLATION",
        reason="capture failed",
        observation={"pane_id": "%0", "capture_ok": False},
        signal={"contract_id": "TEST"},
    )

    second = trail.append(
        incident_id="INC-1",
        component_id="%0",
        evidence_type="ANOMALY",
        reason="pane failed",
    )

    records = trail.records()

    assert len(records) == 2
    assert records[0].evidence_id == first.evidence_id
    assert records[1].evidence_id == second.evidence_id
    assert records[0].incident_id == "INC-1"
    assert records[0].component_id == "%0"


def test_evidence_snapshot_is_isolated_from_source_mutation():
    trail = EvidenceTrail()

    observation = {
        "pane_id": "%0",
        "nested": {"value": "original"},
    }

    trail.append(
        incident_id="INC-2",
        component_id="%0",
        evidence_type="OBSERVATION",
        reason="snapshot test",
        observation=observation,
    )

    observation["nested"]["value"] = "mutated"

    record = trail.records()[0]

    assert record.observation_snapshot["nested"]["value"] == "original"


def test_incident_contract_violation_creates_auditable_evidence():
    manager = IncidentManager()

    observation = {
        "pane_id": "%0",
        "window_name": "test",
        "agent_identity": "TEST",
        "capture_ok": False,
        "pane_dead": False,
    }

    incident = manager.evaluate_contract_violation(
        observation=observation,
        violation_type="CAPTURE_FAILED",
        reason="Sensor capture failed.",
        signal={"source": "TEST"},
    )

    records = incident.get_evidence_records()

    assert len(records) == 1
    assert records[0].incident_id == incident.incident_id
    assert records[0].component_id == "%0"
    assert records[0].evidence_type == "CONTRACT_VIOLATION"
    assert records[0].reason == "Sensor capture failed."
    assert records[0].signal_snapshot["source"] == "TEST"


def test_incident_evidence_accumulates_without_replacement():
    manager = IncidentManager()

    observation = {
        "pane_id": "%1",
        "window_name": "test",
        "agent_identity": "TEST",
        "capture_ok": True,
        "pane_dead": True,
    }

    incident = manager.evaluate_contract_violation(
        observation=observation,
        violation_type="PANE_DEAD",
        reason="Pane is dead.",
        signal={"n": 1},
    )

    manager.evaluate_contract_violation(
        observation=observation,
        violation_type="PANE_DEAD",
        reason="Pane remains dead.",
        signal={"n": 2},
    )

    records = incident.get_evidence_records()

    assert len(records) == 2
    assert records[0].signal_snapshot["n"] == 1
    assert records[1].signal_snapshot["n"] == 2
    assert records[0].evidence_id != records[1].evidence_id


def test_evidence_records_are_immutable():
    trail = EvidenceTrail()

    trail.append(
        incident_id="INC-3",
        component_id="%2",
        evidence_type="OBSERVATION",
        reason="immutable test",
    )

    record = trail.records()[0]

    try:
        record.reason = "tampered"
        raise AssertionError("EvidenceRecord must be immutable")
    except AttributeError:
        pass
