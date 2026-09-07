from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinel.commander import CommanderDecision
from sentinel.diagnostic.commander_handoff import CommanderHandoff
from sentinel.diagnostic.models import (
    Diagnosis,
    DiagnosisStatus,
    InvestigationState,
)
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticConfig,
    RuntimeDiagnosticCoordinator,
)
from sentinel.incidents.manager import Incident
from sentinel.remediation_action_catalog import (
    RemediationActionCatalog,
    RemediationActionEntry,
    RemediationActionSelector,
)
from sentinel.commander_semantic_policy import CommanderSemanticRule
from sentinel.commander import CommanderResult



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
    incident_id="INC-HANDOFF-001",
    component_id="%0",
    anomaly_type="TEST_REMEDIATION_TRIGGER",
):
    return Incident(
        incident_id=incident_id,
        component_id=component_id,
        agent_identity="sentinel-runtime",
        anomaly_type=anomaly_type,
    )


def make_diagnosis(
    investigation_id="investigation-001",
    status=DiagnosisStatus.ESTABLISHED,
):
    return Diagnosis(
        diagnosis_id="diagnosis-001",
        investigation_id=investigation_id,
        conclusion="runtime process is unhealthy",
        status=status,
        supporting_evidence_ids=["evidence-001"],
        contradictory_evidence_ids=[],
        confidence_basis=["evidence-001"],
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

def make_coordinator(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
        str(tmp_path / "diagnostic"),
    )

    return _canonicalize_test_handoff_result(RuntimeDiagnosticCoordinator(
        config=RuntimeDiagnosticConfig(
            max_duration_seconds=60.0,
            max_actions=5,
            max_repeated_action=2,
            max_risk=5,
            minimum_evidence=1,
            cycle_interval_seconds=0.01,
        )
    ))


class CommanderStub:
    def __init__(self):
        self.calls = []
        self.remediate_calls = []

    def decide_remediation(self, *, incident, action):
        self.calls.append((incident, action))
        return CommanderDecision(
            action=action,
            reason="action_authorized",
            authorized=True,
        )

    def remediate(self, **kwargs):
        self.remediate_calls.append(kwargs)
        return "REMEDIATION_EXECUTED"


def test_runtime_handoff_uses_registered_action_only(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    commander = CommanderStub()

    coordinator.commander_handoff = CommanderHandoff(commander)
    coordinator.incident_lookup = lambda incident_id: incident

    incident = make_incident()

    coordinator.remediation_action_catalog.register(
        RemediationActionEntry(
            action="restart_test",
            command="printf 'registered'",
            rationale="controlled test remediation",
        ),
        trigger=incident.anomaly_type,
    )

    investigation = coordinator.register_incident(incident)

    diagnosis = make_diagnosis(
        investigation.investigation_id,
    )

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    handoff = coordinator._handoff_diagnosis(
        investigation,
        diagnosis,
    )

    assert handoff is not None
    assert handoff.request.incident_id == incident.incident_id
    assert handoff.request.diagnosis_id == diagnosis.diagnosis_id
    assert handoff.request.action == "restart_test"
    assert handoff.decision.authorized is True

    assert commander.calls == [
        (incident, "restart_test")
    ]
    assert len(commander.remediate_calls) == 1
    assert commander.remediate_calls[0]["incident"] is incident
    assert commander.remediate_calls[0]["action"] == "restart_test"
    assert commander.remediate_calls[0]["command"] == "printf 'registered'"


def test_runtime_handoff_does_not_generate_command(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    commander = CommanderStub()
    coordinator.commander_handoff = CommanderHandoff(commander)

    incident = make_incident()

    coordinator.incident_lookup = lambda incident_id: incident

    coordinator.remediation_action_catalog.register(
        RemediationActionEntry(
            action="restart_test",
            command="printf 'registered-command'",
            rationale="controlled test remediation",
        ),
        trigger=incident.anomaly_type,
    )

    investigation = coordinator.register_incident(incident)

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    handoff = coordinator._handoff_diagnosis(
        investigation,
        make_diagnosis(investigation.investigation_id),
    )

    assert handoff is not None
    assert not hasattr(handoff.request, "command")
    assert handoff.request.action == "restart_test"
    assert commander.calls == [
        (incident, "restart_test")
    ]
    assert len(commander.remediate_calls) == 1
    assert commander.remediate_calls[0]["incident"] is incident
    assert commander.remediate_calls[0]["action"] == "restart_test"
    assert commander.remediate_calls[0]["command"] == (
        "printf 'registered-command'"
    )


def test_runtime_handoff_requires_established_diagnosis(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    commander = CommanderStub()
    coordinator.commander_handoff = CommanderHandoff(commander)

    incident = make_incident()
    coordinator.incident_lookup = lambda incident_id: incident

    coordinator.remediation_action_catalog.register(
        RemediationActionEntry(
            action="restart_test",
            command="printf 'registered'",
            rationale="controlled test remediation",
        ),
        trigger=incident.anomaly_type,
    )

    investigation = coordinator.register_incident(incident)

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    result = coordinator._handoff_diagnosis(
        investigation,
        make_diagnosis(
            investigation.investigation_id,
            DiagnosisStatus.INSUFFICIENT_EVIDENCE,
        ),
    )

    assert result is None
    assert commander.calls == []
    assert commander.remediate_calls == []


def test_runtime_handoff_requires_registered_action(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    commander = CommanderStub()
    coordinator.commander_handoff = CommanderHandoff(commander)

    incident = make_incident()
    coordinator.incident_lookup = lambda incident_id: incident

    investigation = coordinator.register_incident(incident)

    _register_autonomous_semantic_rule(
        coordinator,
        incident,
    )
    with pytest.raises(
        KeyError,
        match="no remediation action registered",
    ):
        coordinator._handoff_diagnosis(
            investigation,
            make_diagnosis(investigation.investigation_id),
        )

    assert commander.calls == []
    assert commander.remediate_calls == []


def test_runtime_handoff_is_idempotent(
    tmp_path,
    monkeypatch,
):
    coordinator = make_coordinator(tmp_path, monkeypatch)

    commander = CommanderStub()
    coordinator.commander_handoff = CommanderHandoff(commander)

    incident = make_incident()
    coordinator.incident_lookup = lambda incident_id: incident

    coordinator.remediation_action_catalog.register(
        RemediationActionEntry(
            action="restart_test",
            command="printf 'registered'",
            rationale="controlled test remediation",
        ),
        trigger=incident.anomaly_type,
    )

    investigation = coordinator.register_incident(incident)
    diagnosis = make_diagnosis(
        investigation.investigation_id,
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
    assert len(commander.calls) == 1
    assert len(commander.remediate_calls) == 1


def test_runtime_diagnostic_coordinator_has_no_remediation_entrypoint():
    assert not hasattr(
        RuntimeDiagnosticCoordinator,
        "remediate",
    )


def test_commander_handoff_preserves_incident_lifecycle_boundary():
    coordinator = object.__new__(RuntimeDiagnosticCoordinator)

    assert not hasattr(coordinator, "incident_manager")


def test_runtime_commander_wiring_uses_canonical_commander():
    from sentinel.runtime import SentinelRuntime

    runtime = SentinelRuntime()

    assert isinstance(
        runtime.diagnostic.commander_handoff,
        CommanderHandoff,
    )

    assert runtime.diagnostic.incident_lookup is not None
    assert runtime.diagnostic.remediation_action_catalog is not None
