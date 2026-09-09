import json
from copy import deepcopy

import pytest

from sentinel.incident_report_recorder import IncidentReportRecorder
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%recorder"):
    return {
        "pane_id": component_id,
        "window_name": "sentinel-recorder-test",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "c" * 64,
        "agent_identity": "AIRIV_SYSTEM",
    }


def _incident(manager: IncidentManager, component_id: str = "%recorder"):
    return manager.evaluate_anomaly(
        observation=_observation(component_id),
        anomaly_type="FAILED",
        reason="Recorder synthetic failure",
    )


def test_sync_persists_active_incident_report(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    store = IncidentReportStore(tmp_path)

    result = IncidentReportRecorder(store).sync(manager)
    persisted = store.get(incident.incident_id)

    assert result.written_incident_ids == (incident.incident_id,)
    assert result.unchanged_incident_ids == ()
    assert result.report_count == 1
    assert persisted is not None
    assert persisted["incident_id"] == incident.incident_id
    assert persisted["lifecycle_state"] == "OPEN"


def test_second_identical_sync_is_idempotent(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    store = IncidentReportStore(tmp_path)
    recorder = IncidentReportRecorder(store)

    first = recorder.sync(manager)
    second = recorder.sync(manager)

    assert first.written_incident_ids == (incident.incident_id,)
    assert second.written_incident_ids == ()
    assert second.unchanged_incident_ids == (incident.incident_id,)


def test_terminal_transition_rewrites_report_with_final_outcome(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    store = IncidentReportStore(tmp_path)
    recorder = IncidentReportRecorder(store)

    recorder.sync(manager)
    manager.investigate(incident.component_id)
    manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"verified": True, "source": "recorder-test"},
        observation=_observation(incident.component_id),
        final_outcome="RECOVERED",
    )

    result = recorder.sync(manager)
    persisted = store.get(incident.incident_id)

    assert result.written_incident_ids == (incident.incident_id,)
    assert persisted is not None
    assert persisted["lifecycle_state"] == "TERMINAL"
    assert persisted["final_status"] == "RECOVERED"


def test_sync_does_not_mutate_incident_manager_state(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    before_incident = deepcopy(incident.to_dict())
    before_history = manager.get_history()

    IncidentReportRecorder(IncidentReportStore(tmp_path)).sync(manager)

    assert incident.to_dict() == before_incident
    assert manager.get_history() == before_history
    assert manager.get_active_incident(incident.component_id) is incident


def test_corrupt_existing_report_fails_closed_instead_of_overwriting(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    store = IncidentReportStore(tmp_path)
    recorder = IncidentReportRecorder(store)
    recorder.sync(manager)

    path = tmp_path / "reports" / f"{incident.incident_id}.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["report"]["final_status"] = "TAMPERED"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        recorder.sync(manager)

    still_tampered = json.loads(path.read_text(encoding="utf-8"))
    assert still_tampered["report"]["final_status"] == "TAMPERED"


def test_duplicate_active_and_history_identity_fails_closed(tmp_path):
    manager = IncidentManager()
    incident = _incident(manager)
    manager.incident_history.append(deepcopy(incident.to_dict()))

    with pytest.raises(RuntimeError, match="both active state and history"):
        IncidentReportRecorder(IncidentReportStore(tmp_path)).sync(manager)


def test_sync_never_deletes_retained_reports(tmp_path):
    first_manager = IncidentManager()
    incident = _incident(first_manager)
    store = IncidentReportStore(tmp_path)
    recorder = IncidentReportRecorder(store)
    recorder.sync(first_manager)

    empty_manager = IncidentManager()
    result = recorder.sync(empty_manager)

    assert result.report_count == 0
    assert store.get(incident.incident_id) is not None
