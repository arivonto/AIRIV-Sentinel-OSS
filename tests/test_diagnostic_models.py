from datetime import datetime, timezone

from sentinel.diagnostic.models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    Diagnosis,
    DiagnosisStatus,
    Hypothesis,
    HypothesisStatus,
    Investigation,
    InvestigationState,
)


def budget() -> DiagnosticBudget:
    return DiagnosticBudget(
        max_duration_seconds=60,
        max_actions=5,
        max_repeated_action=2,
        max_risk=5,
        minimum_evidence=1,
    )


def test_investigation_has_explicit_identity_and_state():
    item = Investigation(
        investigation_id="inv-001",
        incident_id="inc-001",
        component_id="%2",
        trigger="runtime_anomaly",
        state=InvestigationState.ACTIVE,
        budget=budget(),
    )

    assert item.investigation_id == "inv-001"
    assert item.incident_id == "inc-001"
    assert item.component_id == "%2"
    assert item.state is InvestigationState.ACTIVE


def test_diagnostic_action_identity_is_distinct_from_execution_identity():
    action = DiagnosticAction(
        diagnostic_action_id="diag-001",
        investigation_id="inv-001",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.OBSERVE,
        command="tmux list-panes",
        rationale="Inspect pane state",
        expected_information="Pane liveness",
    )

    assert action.diagnostic_action_id == "diag-001"
    assert not hasattr(action, "execution_id")


def test_diagnostic_action_starts_planned():
    action = DiagnosticAction(
        diagnostic_action_id="diag-002",
        investigation_id="inv-001",
        incident_id="inc-001",
        classification=DiagnosticActionClassification.DIAGNOSTIC,
        command="systemctl status airiv-sentinel.service",
        rationale="Inspect daemon state",
        expected_information="Service health",
    )

    assert action.state is DiagnosticActionState.PLANNED


def test_diagnostic_classification_is_explicit():
    values = {item.value for item in DiagnosticActionClassification}

    assert values == {
        "OBSERVE",
        "DIAGNOSTIC",
        "CONSEQUENTIAL",
        "PROHIBITED",
    }


def test_unknown_is_distinct_from_failed():
    values = {item.value for item in DiagnosticActionState}

    assert "UNKNOWN" in values
    assert "FAILED" not in values


def test_hypothesis_status_tracks_evidence_direction():
    values = {item.value for item in HypothesisStatus}

    assert values == {
        "PROPOSED",
        "SUPPORTED",
        "WEAKENED",
        "CONTRADICTED",
        "UNRESOLVED",
    }


def test_diagnosis_requires_evidence_basis():
    diagnosis = Diagnosis(
        diagnosis_id="diagnosis-001",
        investigation_id="inv-001",
        conclusion="process became unresponsive",
        status=DiagnosisStatus.ESTABLISHED,
        supporting_evidence_ids=["evidence-001"],
        confidence_basis=["evidence-001"],
    )

    assert diagnosis.supporting_evidence_ids == ["evidence-001"]
    assert diagnosis.confidence_basis == ["evidence-001"]


def test_budget_is_hard_bounded():
    item = budget()

    assert not item.exhausted()

    item.consumed_actions = 5

    assert item.exhausted()


def test_model_timestamps_are_timezone_aware():
    item = Investigation(
        investigation_id="inv-002",
        incident_id="inc-002",
        component_id="%3",
        trigger="test",
        state=InvestigationState.ACTIVE,
        budget=budget(),
    )

    assert item.created_at.tzinfo is not None
    assert item.created_at.utcoffset() is not None
    assert item.created_at.utcoffset() == timezone.utc.utcoffset(item.created_at)
