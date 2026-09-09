from copy import deepcopy

import pytest

from sentinel.runtime import SentinelRuntime


def _observation(component_id: str = "%runtime-report"):
    return {
        "pane_id": component_id,
        "window_name": "sentinel-test",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "b" * 64,
        "agent_identity": "AIRIV_SYSTEM",
    }


def _active_incident(runtime: SentinelRuntime):
    return runtime.incident_manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Runtime report synthetic failure",
        signal={"source": "runtime-report-test"},
    )


class _ForbiddenBoundary:
    def __getattr__(self, name):
        raise AssertionError(f"reporting touched forbidden boundary: {name}")


def test_runtime_reads_active_incident_report_without_lifecycle_mutation():
    runtime = SentinelRuntime()
    incident = _active_incident(runtime)
    before = deepcopy(incident.to_dict())

    report = runtime.get_incident_report(incident.incident_id)

    assert incident.to_dict() == before
    assert report.payload["incident_id"] == incident.incident_id
    assert report.payload["lifecycle_state"] == "OPEN"
    assert report.payload["final_status"] == "OPEN"
    assert runtime.running is False


def test_runtime_reads_terminal_report_from_canonical_history():
    runtime = SentinelRuntime()
    incident = _active_incident(runtime)

    runtime.incident_manager.resolve(
        component_id=incident.component_id,
        recovery_evidence={"verified": True, "source": "runtime-test"},
        observation=_observation(),
        final_outcome="RECOVERED",
    )

    report = runtime.get_incident_report(incident.incident_id)

    assert runtime.incident_manager.get_incident_by_id(incident.incident_id) is None
    assert report.payload["lifecycle_state"] == "TERMINAL"
    assert report.payload["final_outcome"] == "RECOVERED"
    assert report.payload["final_status"] == "RECOVERED"
    assert "# AIRIV Sentinel Incident Report" in report.to_markdown()


def test_runtime_reporting_does_not_touch_policy_commander_or_execution():
    runtime = SentinelRuntime()
    incident = _active_incident(runtime)
    before = deepcopy(incident.to_dict())

    runtime.policy = _ForbiddenBoundary()
    runtime.commander = _ForbiddenBoundary()
    runtime.execution = _ForbiddenBoundary()
    runtime.gate = _ForbiddenBoundary()
    runtime.orchestrator = _ForbiddenBoundary()

    report = runtime.get_incident_report(incident.incident_id)

    assert report.payload["incident_id"] == incident.incident_id
    assert incident.to_dict() == before


def test_runtime_reporting_unknown_incident_fails_closed():
    runtime = SentinelRuntime()
    history_before = runtime.incident_manager.get_history()

    with pytest.raises(KeyError, match="Unknown incident_id"):
        runtime.get_incident_report("INC-does-not-exist")

    assert runtime.incident_manager.get_history() == history_before
    assert runtime.incident_manager.get_active_incident("%runtime-report") is None
