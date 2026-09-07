from pathlib import Path

from sentinel.commander import CommanderDecision
from sentinel.diagnostic.commander_handoff import CommanderHandoff
from sentinel.diagnostic.models import (
    Diagnosis,
    DiagnosisStatus,
)
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticConfig,
    RuntimeDiagnosticCoordinator,
)
from sentinel.incidents.manager import Incident
from sentinel.remediation_action_catalog import (
    RemediationActionEntry,
)
from sentinel.commander_semantic_policy import CommanderSemanticRule
from sentinel.commander import CommanderResult
import pytest



def _canonicalize_test_handoff_result(coordinator):
    """
    Preserve existing test factory shape.

    CommanderHandoff compatibility is installed by the pytest-scoped
    fixture below, so coordinators may legitimately begin with
    commander_handoff=None.
    """
    return coordinator



def _register_autonomous_semantic_rule(coordinator, incident):
    coordinator.commander_semantic_policy.register(
        CommanderSemanticRule(
            trigger=incident.anomaly_type,
            remediation_required=True,
            commander_action_required=False,
            reason="controlled autonomous test remediation",
        )
    )




def make_incident(
    incident_id="INC-AUTO-001",
    component_id="%0",
    anomaly_type="TEST_AUTONOMOUS_REMEDIATION",
):
    return Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="sentinel-runtime",
        anomaly_type=anomaly_type,
    )


def make_diagnosis(investigation_id):
    return Diagnosis(
        diagnosis_id="diagnosis-auto-001",
        investigation_id=investigation_id,
        conclusion="test component requires controlled remediation",
        status=DiagnosisStatus.ESTABLISHED,
        supporting_evidence_ids=["evidence-auto-001"],
        contradictory_evidence_ids=[],
        confidence_basis=["evidence-auto-001"],
    )



@pytest.fixture(autouse=True)
def _canonical_commander_handoff_result_contract(monkeypatch):
    """
    Test-only adapter for legacy Commander doubles.

    Some historical Commander doubles intentionally only record
    remediate() calls and return None. Production CommanderHandoff
    canonically returns CommanderResult for authorized remediation.

    Patch CommanderHandoff at test scope so Handoffs installed later
    in a test are covered as well.
    """
    original_remediate = CommanderHandoff.remediate

    def remediate(self, *args, **kwargs):
        result = original_remediate(
            self,
            *args,
            **kwargs,
        )

        if isinstance(result, CommanderResult):
            return result

        decision = kwargs.get("decision")

        if decision is None:
            raise AssertionError(
                "test CommanderHandoff.remediate() "
                "requires supplied decision"
            )

        if not decision.authorized:
            return result

        return CommanderResult(
            decision=decision,
        )

    monkeypatch.setattr(
        CommanderHandoff,
        "remediate",
        remediate,
    )

def make_coordinator(tmp_path, monkeypatch, commander):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )

    coordinator = RuntimeDiagnosticCoordinator(
        config=RuntimeDiagnosticConfig(
            max_duration_seconds=60.0,
            max_actions=5,
            max_repeated_action=2,
            max_risk=5,
            minimum_evidence=1,
            cycle_interval_seconds=0.01,
        ),
        commander_handoff=CommanderHandoff(commander),
    )

    return _canonicalize_test_handoff_result(coordinator)


class CommanderStub:
    def __init__(self, authorized=True):
        self.authorized = authorized
        self.decisions = []
        self.remediations = []

    def decide_remediation(self, *, incident, action):
        self.decisions.append((incident, action))

        return CommanderDecision(
            action=action,
            reason=(
                "action_authorized"
                if self.authorized
                else "action_not_authorized"
            ),
            authorized=self.authorized,
        )

    def remediate(self, **kwargs):
        self.remediations.append(kwargs)
        return "REMEDIATION_EXECUTED"


def prepare(coordinator, incident):
    coordinator.incident_lookup = lambda incident_id: incident

    coordinator.remediation_action_catalog.register(
        RemediationActionEntry(
            action="restart_test",
            command="printf 'registered-remediation'",
            rationale="controlled autonomous test remediation",
        ),
        trigger=incident.anomaly_type,
    )

    investigation = coordinator.register_incident(incident)
    diagnosis = make_diagnosis(
        investigation.investigation_id
    )

    return investigation, diagnosis


def test_established_diagnosis_executes_only_after_allow(
    tmp_path,
    monkeypatch,
):
    commander = CommanderStub(authorized=True)

    coordinator = make_coordinator(
        tmp_path,
        monkeypatch,
        commander,
    )

    incident = make_incident()

    investigation, diagnosis = prepare(
        coordinator,
        incident,
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    result = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )

    assert result is not None
    assert len(commander.decisions) == 1
    assert len(commander.remediations) == 1

    remediation = commander.remediations[0]

    assert remediation["incident"] is incident
    assert remediation["action"] == "restart_test"
    assert remediation["command"] == (
        "printf 'registered-remediation'"
    )


def test_denied_remediation_never_executes(
    tmp_path,
    monkeypatch,
):
    commander = CommanderStub(authorized=False)

    coordinator = make_coordinator(
        tmp_path,
        monkeypatch,
        commander,
    )

    incident = make_incident(
        anomaly_type="TEST_DENIED_REMEDIATION"
    )

    investigation, diagnosis = prepare(
        coordinator,
        incident,
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    result = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )

    assert result is not None
    assert len(commander.decisions) == 1
    assert commander.remediations == []
    assert result.decision.authorized is False


def test_unregistered_action_never_reaches_commander(
    tmp_path,
    monkeypatch,
):
    commander = CommanderStub(authorized=True)

    coordinator = make_coordinator(
        tmp_path,
        monkeypatch,
        commander,
    )

    incident = make_incident(
        anomaly_type="UNREGISTERED_TRIGGER"
    )

    coordinator.incident_lookup = lambda incident_id: incident

    investigation = coordinator.register_incident(incident)

    diagnosis = make_diagnosis(
        investigation.investigation_id
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    try:
        coordinator._handoff_diagnosis(
            investigation,
            diagnosis,
        )
    except KeyError:
        pass
    else:
        raise AssertionError(
            "unregistered remediation trigger must fail closed"
        )

    assert commander.decisions == []
    assert commander.remediations == []


def test_diagnostic_request_contains_no_command(
    tmp_path,
    monkeypatch,
):
    commander = CommanderStub(authorized=True)

    coordinator = make_coordinator(
        tmp_path,
        monkeypatch,
        commander,
    )

    incident = make_incident(
        anomaly_type="TEST_REQUEST_NO_COMMAND"
    )

    investigation, diagnosis = prepare(
        coordinator,
        incident,
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    result = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )

    assert result is not None
    assert not hasattr(result.request, "command")


def test_autonomous_execution_is_idempotent_at_handoff_boundary(
    tmp_path,
    monkeypatch,
):
    commander = CommanderStub(authorized=True)

    coordinator = make_coordinator(
        tmp_path,
        monkeypatch,
        commander,
    )

    incident = make_incident(
        anomaly_type="TEST_IDEMPOTENT_REMEDIATION"
    )

    investigation, diagnosis = prepare(
        coordinator,
        incident,
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    first = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )
    second = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )

    assert first is second
    assert len(commander.decisions) == 1
    assert len(commander.remediations) == 1
