from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sentinel.diagnostic.evidence import (
    DiagnosticEvidenceRecord,
    EvidenceAdapter,
)
from sentinel.diagnostic.executor import DiagnosticResult
from sentinel.diagnostic.investigation import InvestigationManager
from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    InvestigationState,
    Observation,
)
from sentinel.diagnostic.store import InvestigationStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_manager(tmp_path):
    store = InvestigationStore(tmp_path)
    return InvestigationManager(store)


def make_investigation(manager):
    budget = DiagnosticBudget(
        max_duration_seconds=60,
        max_actions=10,
        max_repeated_action=3,
        max_risk=10,
        minimum_evidence=1,
    )

    return manager.start(
        incident_id="incident-001",
        component_id="component-001",
        trigger="test-trigger",
        budget=budget,
        investigation_id="investigation-001",
    )


def make_action(investigation):
    return DiagnosticAction(
        diagnostic_action_id="action-001",
        investigation_id=investigation.investigation_id,
        incident_id=investigation.incident_id,
        classification=DiagnosticActionClassification.DIAGNOSTIC,
        command="echo diagnostic",
        rationale="test diagnostic action",
        expected_information="diagnostic output",
        state=DiagnosticActionState.COMPLETED,
    )


def make_result(action):
    now = utc_now()

    return DiagnosticResult(
        diagnostic_action_id=action.diagnostic_action_id,
        command=action.command,
        started_at=now,
        finished_at=now,
        stdout="diagnostic output",
        stderr="",
        exit_code=0,
        success=True,
        state="COMPLETED",
    )


def make_observation(investigation, action):
    return Observation(
        observation_id="observation-001",
        investigation_id=investigation.investigation_id,
        diagnostic_action_id=action.diagnostic_action_id,
        component_id=investigation.component_id,
        observed_at=utc_now(),
        source="diagnostic_executor",
        subject="command_output",
        value="diagnostic output",
        raw_evidence={"stdout": "diagnostic output"},
    )


def test_record_diagnostic_result_creates_immutable_record(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    result = make_result(action)

    adapter = EvidenceAdapter(manager)
    record = adapter.record_diagnostic_result(
        investigation,
        action,
        result,
    )

    assert isinstance(record, DiagnosticEvidenceRecord)
    assert record.evidence_id == (
        "diagnostic:investigation-001:action-001"
    )
    assert record.investigation_id == "investigation-001"
    assert record.incident_id == "incident-001"
    assert record.diagnostic_action_id == "action-001"
    assert record.classification == "DIAGNOSTIC"
    assert record.command == "echo diagnostic"
    assert record.stdout == "diagnostic output"
    assert record.success is True
    assert record.state == "COMPLETED"

    refreshed = manager.get("investigation-001")
    assert refreshed is not None
    assert "diagnostic:investigation-001:action-001" in refreshed.evidence_ids


def test_record_diagnostic_result_with_observation_links_observation(
    tmp_path,
):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    observation = make_observation(investigation, action)
    manager.record_observation(
        investigation.investigation_id,
        observation,
    )

    result = make_result(action)

    adapter = EvidenceAdapter(manager)
    record = adapter.record_diagnostic_result(
        investigation,
        action,
        result,
        observation=observation,
    )

    assert record.observation_id == "observation-001"


def test_record_diagnostic_result_rejects_investigation_mismatch(
    tmp_path,
):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)

    other_investigation = manager.start(
        incident_id="incident-002",
        component_id="component-002",
        trigger="other-trigger",
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=10,
            max_repeated_action=3,
            max_risk=10,
            minimum_evidence=1,
        ),
        investigation_id="investigation-002",
    )

    action = make_action(other_investigation)
    result = make_result(action)

    adapter = EvidenceAdapter(manager)

    with pytest.raises(ValueError, match="investigation_id_mismatch"):
        adapter.record_diagnostic_result(
            investigation,
            action,
            result,
        )


def test_record_diagnostic_result_rejects_incident_mismatch(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)

    action = DiagnosticAction(
        diagnostic_action_id="action-001",
        investigation_id=investigation.investigation_id,
        incident_id="incident-999",
        classification=DiagnosticActionClassification.DIAGNOSTIC,
        command="echo diagnostic",
        rationale="test diagnostic action",
        expected_information="diagnostic output",
        state=DiagnosticActionState.COMPLETED,
    )

    result = make_result(action)

    adapter = EvidenceAdapter(manager)

    with pytest.raises(ValueError, match="incident_id_mismatch"):
        adapter.record_diagnostic_result(
            investigation,
            action,
            result,
        )


def test_record_diagnostic_result_rejects_result_action_mismatch(
    tmp_path,
):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)

    result = DiagnosticResult(
        diagnostic_action_id="action-999",
        command=action.command,
        started_at=utc_now(),
        finished_at=utc_now(),
        stdout="diagnostic output",
        stderr="",
        exit_code=0,
        success=True,
        state="COMPLETED",
    )

    adapter = EvidenceAdapter(manager)

    with pytest.raises(
        ValueError,
        match="diagnostic_action_id_mismatch",
    ):
        adapter.record_diagnostic_result(
            investigation,
            action,
            result,
        )


def test_record_observation_delegates_to_investigation_manager(
    tmp_path,
):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    observation = make_observation(investigation, action)

    adapter = EvidenceAdapter(manager)
    adapter.record_observation(
        investigation,
        observation,
    )

    refreshed = manager.get("investigation-001")

    assert refreshed is not None
    assert "observation-001" in refreshed.observation_ids


def test_record_observation_rejects_investigation_mismatch(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)

    observation = Observation(
        observation_id="observation-001",
        investigation_id="investigation-999",
        diagnostic_action_id="action-001",
        component_id=investigation.component_id,
        observed_at=utc_now(),
        source="diagnostic_executor",
        subject="command_output",
        value="diagnostic output",
    )

    adapter = EvidenceAdapter(manager)

    with pytest.raises(ValueError, match="investigation_id_mismatch"):
        adapter.record_observation(
            investigation,
            observation,
        )


def test_record_observation_rejects_component_mismatch(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    observation = Observation(
        observation_id="observation-001",
        investigation_id=investigation.investigation_id,
        diagnostic_action_id=action.diagnostic_action_id,
        component_id="component-999",
        observed_at=utc_now(),
        source="diagnostic_executor",
        subject="command_output",
        value="diagnostic output",
    )

    adapter = EvidenceAdapter(manager)

    with pytest.raises(ValueError, match="observation component_id mismatch"):
        adapter.record_observation(
            investigation,
            observation,
        )


def test_evidence_record_is_frozen(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    result = make_result(action)

    adapter = EvidenceAdapter(manager)
    record = adapter.record_diagnostic_result(
        investigation,
        action,
        result,
    )

    with pytest.raises(AttributeError):
        record.stdout = "tampered"


def test_failed_diagnostic_result_is_preserved_as_evidence(tmp_path):
    manager = make_manager(tmp_path)
    investigation = make_investigation(manager)
    action = make_action(investigation)
    manager.record_action(investigation.investigation_id, action)

    result = DiagnosticResult(
        diagnostic_action_id=action.diagnostic_action_id,
        command=action.command,
        started_at=utc_now(),
        finished_at=utc_now(),
        stdout="",
        stderr="diagnostic failure",
        exit_code=1,
        success=False,
        state="COMPLETED",
    )

    adapter = EvidenceAdapter(manager)
    record = adapter.record_diagnostic_result(
        investigation,
        action,
        result,
    )

    assert record.success is False
    assert record.exit_code == 1
    assert record.stderr == "diagnostic failure"
    assert record.state == "COMPLETED"
