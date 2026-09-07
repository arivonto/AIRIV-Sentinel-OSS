from unittest.mock import Mock

import pytest

from sentinel.diagnostic.commander_handoff import (
    CommanderHandoff,
    RemediationActionRequest,
)
from sentinel.diagnostic.models import Diagnosis, DiagnosisStatus


from sentinel.incidents.manager import Incident

def make_incident(
    incident_id: str = "incident-1",
    component_id: str = "component-1",
    anomaly_type: str = "test_anomaly",
):
    return Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="test-agent",
        anomaly_type=anomaly_type,
    )

def make_diagnosis(
    status=DiagnosisStatus.ESTABLISHED,
):
    return Diagnosis(
        diagnosis_id="diagnosis-001",
        investigation_id="investigation-001",
        conclusion="runtime process is unhealthy",
        status=status,
        supporting_evidence_ids=["evidence-001"],
        contradictory_evidence_ids=[],
        confidence_basis=["evidence-001"],
    )


class IncidentStub:
    def __init__(self, incident_id="incident-001"):
        self.incident_id = incident_id


def test_established_diagnosis_creates_action_request_without_command():
    diagnosis = make_diagnosis()

    request = RemediationActionRequest.from_diagnosis(
        incident_id="incident-001",
        diagnosis=diagnosis,
        action="restart_test",
    )

    assert request.incident_id == "incident-001"
    assert request.investigation_id == "investigation-001"
    assert request.diagnosis_id == "diagnosis-001"
    assert request.action == "restart_test"
    assert request.reason == "runtime process is unhealthy"
    assert request.supporting_evidence_ids == ("evidence-001",)
    assert not hasattr(request, "command")


def test_non_established_diagnosis_cannot_be_handed_off():
    diagnosis = make_diagnosis(
        DiagnosisStatus.INSUFFICIENT_EVIDENCE,
    )

    with pytest.raises(ValueError, match="ESTABLISHED"):
        RemediationActionRequest.from_diagnosis(
            incident_id="incident-001",
            diagnosis=diagnosis,
            action="restart_test",
        )


def test_handoff_calls_only_commander_decision_boundary():
    commander = Mock()
    commander.decide_remediation.return_value = "DECISION"

    handoff = CommanderHandoff(commander)

    request = RemediationActionRequest.from_diagnosis(
        incident_id="incident-001",
        diagnosis=make_diagnosis(),
        action="restart_test",
    )

    incident = IncidentStub()

    result = handoff.decide(request, incident)

    assert result == "DECISION"

    commander.decide_remediation.assert_called_once_with(
        incident=incident,
        action="restart_test",
    )


def test_handoff_does_not_call_remediate():
    commander = Mock()
    commander.decide_remediation.return_value = "DECISION"

    handoff = CommanderHandoff(commander)

    request = RemediationActionRequest.from_diagnosis(
        incident_id="incident-001",
        diagnosis=make_diagnosis(),
        action="restart_test",
    )

    handoff.decide(request, IncidentStub())

    commander.remediate.assert_not_called()


def test_handoff_rejects_incident_mismatch():
    commander = Mock()
    handoff = CommanderHandoff(commander)

    request = RemediationActionRequest.from_diagnosis(
        incident_id="incident-001",
        diagnosis=make_diagnosis(),
        action="restart_test",
    )

    with pytest.raises(ValueError, match="incident_id mismatch"):
        handoff.decide(
            request,
            IncidentStub("different-incident"),
        )


def test_action_request_does_not_contain_executable_command():
    request = RemediationActionRequest.from_diagnosis(
        incident_id="incident-001",
        diagnosis=make_diagnosis(),
        action="restart_test",
    )

    fields = request.__dataclass_fields__

    assert "command" not in fields
    assert "shell_command" not in fields
    assert "executable" not in fields


def test_handoff_can_execute_authorized_remediation():
    from sentinel.diagnostic.commander_handoff import (
        CommanderHandoff,
        RemediationActionRequest,
    )

    class CommanderStub:
        def __init__(self):
            self.decisions = []
            self.remediations = []

        def decide_remediation(self, *, incident, action):
            from sentinel.commander import CommanderDecision

            self.decisions.append((incident, action))

            return CommanderDecision(
                action=action,
                reason="action_authorized",
                authorized=True,
            )

        def remediate(self, **kwargs):
            self.remediations.append(kwargs)
            return "EXECUTED"

    commander = CommanderStub()
    handoff = CommanderHandoff(commander)

    incident = make_incident()
    diagnosis = make_diagnosis()

    request = RemediationActionRequest.from_diagnosis(
        incident_id=incident.incident_id,
        diagnosis=diagnosis,
        action="restart_test",
    )

    decision = handoff.decide(
        request=request,
        incident=incident,
    )

    result = handoff.remediate(
        request=request,
        incident=incident,
        command="printf 'authorized'",
        decision=decision,
    )

    assert result == "EXECUTED"
    assert len(commander.decisions) == 1
    assert len(commander.remediations) == 1
    assert commander.remediations[0]["action"] == "restart_test"
    assert commander.remediations[0]["command"] == "printf 'authorized'"
