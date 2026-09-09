import json

import pytest

from sentinel.incident_report_store import IncidentReportStore
from sentinel.incident_reporting import IncidentReportBuilder
from sentinel.incidents.manager import IncidentManager


def _observation(component_id: str = "%store-report"):
    return {
        "pane_id": component_id,
        "window_name": "sentinel-test",
        "current_command": "python",
        "activity_state": "FAILED",
        "output_sha256": "c" * 64,
        "agent_identity": "AIRIV_SYSTEM",
    }


def _report(incident_id: str | None = None):
    if incident_id is not None:
        return IncidentReportBuilder().build(
            {
                "incident_id": incident_id,
                "component_id": "%store-report",
                "agent_identity": "AIRIV_SYSTEM",
                "anomaly_type": "FAILED",
                "created_at": "2026-09-09T00:00:00+00:00",
                "updated_at": "2026-09-09T00:00:01+00:00",
                "status": "OPEN",
                "final_outcome": None,
                "evidence_trail": [],
            }
        )

    manager = IncidentManager()
    incident = manager.evaluate_anomaly(
        observation=_observation(),
        anomaly_type="FAILED",
        reason="Durable store synthetic failure",
        signal={"source": "incident-report-store-test"},
    )
    return IncidentReportBuilder().build(incident)


def test_report_survives_store_reload(tmp_path):
    report = _report()
    store = IncidentReportStore(tmp_path)

    store.save(report)
    reloaded = IncidentReportStore(tmp_path).get(
        report.payload["incident_id"]
    )

    assert reloaded is not None
    assert reloaded == report.to_dict()
    assert reloaded is not report.to_dict()


def test_store_lists_and_recovers_reports_deterministically(tmp_path):
    store = IncidentReportStore(tmp_path)
    second = _report("INC-b")
    first = _report("INC-a")

    store.save(second)
    store.save(first)

    assert store.list_incident_ids() == ["INC-a", "INC-b"]
    recovered = store.recover()
    assert [item["incident_id"] for item in recovered] == [
        "INC-a",
        "INC-b",
    ]


def test_store_rejects_unsafe_incident_id_without_path_escape(tmp_path):
    store = IncidentReportStore(tmp_path / "store")
    unsafe = _report("../escape")

    with pytest.raises(ValueError, match="unsafe path characters"):
        store.save(unsafe)

    assert not (tmp_path / "escape.json").exists()
    assert store.list_incident_ids() == []


def test_store_detects_payload_tampering(tmp_path):
    report = _report("INC-tamper")
    store = IncidentReportStore(tmp_path)
    store.save(report)

    path = tmp_path / "reports" / "INC-tamper.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["report"]["final_status"] = "RECOVERED"
    path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        store.get("INC-tamper")


def test_store_fails_closed_for_malformed_envelope(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    path = reports_dir / "INC-malformed.json"
    path.write_text(
        json.dumps(
            {
                "store_schema_version": "WRONG",
                "report_sha256": "0" * 64,
                "report": {},
            }
        ),
        encoding="utf-8",
    )

    store = IncidentReportStore(tmp_path)
    with pytest.raises(ValueError, match="unsupported incident report store"):
        store.get("INC-malformed")


def test_missing_report_returns_none_and_empty_recovery(tmp_path):
    store = IncidentReportStore(tmp_path)

    assert store.get("INC-missing") is None
    assert store.list_incident_ids() == []
    assert store.recover() == []


def test_atomic_save_leaves_no_temporary_file_and_preserves_report(tmp_path):
    report = _report("INC-atomic")
    before = report.to_dict()
    store = IncidentReportStore(tmp_path)

    store.save(report)

    assert report.to_dict() == before
    reports_dir = tmp_path / "reports"
    assert list(reports_dir.glob("*.tmp")) == []
    assert (reports_dir / "INC-atomic.json").is_file()
