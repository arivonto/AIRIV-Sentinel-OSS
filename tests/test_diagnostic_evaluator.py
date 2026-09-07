from datetime import datetime, timezone

import pytest

from sentinel.diagnostic.evaluator import DiagnosisEvaluator
from sentinel.diagnostic.models import (
    DiagnosticBudget,
    DiagnosisStatus,
    Hypothesis,
    HypothesisStatus,
    Investigation,
    InvestigationState,
)


def make_investigation(
    *,
    evidence_ids=None,
    minimum_evidence=2,
):
    return Investigation(
        investigation_id="inv-001",
        incident_id="inc-001",
        component_id="pane-1",
        trigger="test failure",
        state=InvestigationState.ACTIVE,
        budget=DiagnosticBudget(
            max_duration_seconds=60,
            max_actions=10,
            max_repeated_action=3,
            max_risk=10,
            minimum_evidence=minimum_evidence,
        ),
        evidence_ids=list(evidence_ids or []),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def make_hypothesis(
    *,
    status=HypothesisStatus.PROPOSED,
    supporting=None,
    contradicting=None,
):
    return Hypothesis(
        hypothesis_id="hyp-001",
        investigation_id="inv-001",
        statement="runtime process is unhealthy",
        status=status,
        supporting_evidence_ids=list(supporting or []),
        contradicting_evidence_ids=list(contradicting or []),
    )


def test_insufficient_when_minimum_evidence_not_met():
    investigation = make_investigation(
        evidence_ids=["evidence-1"],
        minimum_evidence=2,
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.conclusion == ""
    assert diagnosis.supporting_evidence_ids == []


def test_insufficient_without_supported_hypothesis():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.PROPOSED,
        supporting=["evidence-1"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.conclusion == ""


def test_established_with_minimum_evidence_and_supported_hypothesis():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1", "evidence-2"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.ESTABLISHED
    assert diagnosis.conclusion == "runtime process is unhealthy"
    assert diagnosis.supporting_evidence_ids == [
        "evidence-1",
        "evidence-2",
    ]


def test_insufficient_when_supporting_evidence_is_not_in_investigation():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1", "fabricated-evidence"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.conclusion == ""


def test_insufficient_when_support_and_contradiction_share_evidence():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1"],
        contradicting=["evidence-1"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.conclusion == ""


def test_unrelated_hypothesis_is_ignored():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )

    foreign_hypothesis = Hypothesis(
        hypothesis_id="foreign-hypothesis",
        investigation_id="different-investigation",
        statement="foreign conclusion",
        status=HypothesisStatus.SUPPORTED,
        supporting_evidence_ids=["evidence-1", "evidence-2"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [foreign_hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.INSUFFICIENT_EVIDENCE


def test_diagnosis_contains_only_supporting_evidence():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2", "evidence-3"],
    )

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1", "evidence-2"],
    )

    diagnosis = DiagnosisEvaluator().evaluate(
        investigation,
        [hypothesis],
    )

    assert diagnosis.status == DiagnosisStatus.ESTABLISHED
    assert diagnosis.supporting_evidence_ids == [
        "evidence-1",
        "evidence-2",
    ]
    assert "evidence-3" not in diagnosis.supporting_evidence_ids


def test_evaluator_does_not_create_execution_authority():
    evaluator = DiagnosisEvaluator()

    public_methods = {
        name
        for name in dir(evaluator)
        if not name.startswith("_")
    }

    assert public_methods == {"evaluate"}


def test_empty_investigation_id_is_rejected():
    investigation = make_investigation(
        evidence_ids=["evidence-1", "evidence-2"],
    )
    investigation.investigation_id = ""

    hypothesis = make_hypothesis(
        status=HypothesisStatus.SUPPORTED,
        supporting=["evidence-1", "evidence-2"],
    )

    with pytest.raises(ValueError, match="investigation_id is required"):
        DiagnosisEvaluator().evaluate(
            investigation,
            [hypothesis],
        )
