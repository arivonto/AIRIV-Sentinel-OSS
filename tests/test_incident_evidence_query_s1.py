from copy import deepcopy

import pytest

from sentinel.incident_evidence import EvidenceCompleteIncidentReportBuilder
from sentinel.incident_evidence_query import (
    IncidentEvidenceQuery,
    IncidentEvidenceQueryService,
)
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incidents.manager import Incident


def _incident(incident_id: str, component_id: str, *, commander: bool = False) -> Incident:
    incident = Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="AIRIV_SYSTEM",
        anomaly_type="FAILED",
    )
    incident.add_evidence(
        {
            "pane_id": component_id,
            "window_name": "lane-2-query-fixture",
            "current_command": "python",
            "activity_state": "FAILED",
            "output_sha256": "e" * 64,
            "agent_identity": "AIRIV_SYSTEM",
        },
        "Deterministic query fixture detected.",
        "ANOMALY",
        {"observed_state": "FAILED"},
    )
    if commander:
        incident.add_evidence(
            {},
            "Commander decision required by fixture.",
            "COMMANDER_HANDOFF",
            {
                "commander_required": True,
                "decision": "WAIT_FOR_COMMANDER",
            },
        )
    return incident


def _store(tmp_path):
    store = IncidentReportStore(tmp_path / "reports")
    builder = EvidenceCompleteIncidentReportBuilder()

    first = _incident("INC-LANE2-Q-001", "%31", commander=True)
    second = _incident("INC-LANE2-Q-002", "%32", commander=False)

    store.save(builder.build(first))
    store.save(builder.build(second))
    return store


def test_get_returns_integrity_checked_read_only_report(tmp_path):
    store = _store(tmp_path)
    service = IncidentEvidenceQueryService(store)

    report = service.get("INC-LANE2-Q-001")

    assert report is not None
    assert report["incident_id"] == "INC-LANE2-Q-001"
    assert report["component_id"] == "%31"
    assert report["commander_decision_requirement"]["required"] is True

    with pytest.raises(TypeError):
        report["incident_id"] = "tampered"
    with pytest.raises(TypeError):
        report["timeline"][0]["reason"] = "tampered"

    assert service.get("INC-LANE2-Q-MISSING") is None


def test_search_filters_commander_component_signal_and_source(tmp_path):
    store = _store(tmp_path)
    service = IncidentEvidenceQueryService(store)

    result = service.search(
        IncidentEvidenceQuery(
            component_id="%31",
            commander_required=True,
            signal_types=("commander_handoff",),
            sources=("incident_evidence",),
        )
    )

    assert len(result) == 1
    item = result.items[0]
    assert item["incident_id"] == "INC-LANE2-Q-001"
    assert item["matched_event_count"] == 1
    assert item["matched_events"][0]["signal_type"] == "COMMANDER_HANDOFF"
    assert item["matched_events"][0]["source"] == "INCIDENT_EVIDENCE"

    exported = result.to_list()
    exported[0]["incident_id"] = "changed-copy"
    assert result.items[0]["incident_id"] == "INC-LANE2-Q-001"


def test_search_by_incident_id_uses_exact_read_path(tmp_path):
    store = _store(tmp_path)
    service = IncidentEvidenceQueryService(store)

    result = service.search(
        IncidentEvidenceQuery(incident_id="INC-LANE2-Q-002")
    )

    assert len(result) == 1
    assert result.items[0]["incident_id"] == "INC-LANE2-Q-002"
    assert result.items[0]["component_id"] == "%32"

    missing = service.search(
        IncidentEvidenceQuery(incident_id="INC-LANE2-Q-MISSING")
    )
    assert len(missing) == 0


def test_event_filter_excludes_reports_without_matching_evidence(tmp_path):
    store = _store(tmp_path)
    service = IncidentEvidenceQueryService(store)

    result = service.search(
        IncidentEvidenceQuery(signal_types=("DIAGNOSTIC_FAILURE",))
    )

    assert len(result) == 0


def test_query_validation_rejects_invalid_ranges_and_values():
    with pytest.raises(ValueError, match="incident_id"):
        IncidentEvidenceQuery(incident_id="")
    with pytest.raises(ValueError, match="final_statuses"):
        IncidentEvidenceQuery(final_statuses=("",))
    with pytest.raises(ValueError, match="started_before"):
        IncidentEvidenceQuery(
            started_at_or_after="2026-09-10T10:00:00+00:00",
            started_before="2026-09-10T09:00:00+00:00",
        )
    with pytest.raises(ValueError, match="event_before"):
        IncidentEvidenceQuery(
            event_at_or_after="2026-09-10T10:00:00+00:00",
            event_before="2026-09-10T10:00:00+00:00",
        )


def test_corrupt_timeline_fails_closed_instead_of_being_skipped(tmp_path):
    store = _store(tmp_path)
    valid = store.get("INC-LANE2-Q-001")
    assert valid is not None

    corrupt = deepcopy(valid)
    corrupt["timeline"][0]["reason"] = "tampered after integrity seal"

    class CorruptStore:
        def get(self, incident_id):
            return deepcopy(corrupt) if incident_id == corrupt["incident_id"] else None

        def recover(self):
            return [deepcopy(corrupt)]

    service = IncidentEvidenceQueryService(CorruptStore())

    with pytest.raises(ValueError, match="integrity"):
        service.get("INC-LANE2-Q-001")
    with pytest.raises(ValueError, match="integrity"):
        service.search()


def test_store_surface_is_not_mutated_by_queries(tmp_path):
    store = _store(tmp_path)
    before = store.recover()
    service = IncidentEvidenceQueryService(store)

    service.get("INC-LANE2-Q-001")
    service.search(IncidentEvidenceQuery(commander_required=True))
    service.search(IncidentEvidenceQuery(component_id="%32"))

    assert store.recover() == before
