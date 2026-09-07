from sentinel.commander_intent_assessment import (
    CommanderIntentAssessment,
)
from sentinel.commander_intent_assessor import (
    CommanderIntentAssessor,
)
from sentinel.diagnostic.models import DiagnosisStatus


def test_assessor_produces_explicit_facts():
    result = CommanderIntentAssessor().assess(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_required=True,
        remediation_action_available=True,
        commander_action_required=False,
    )

    assert isinstance(result, CommanderIntentAssessment)
    assert result.diagnosis_status is DiagnosisStatus.ESTABLISHED
    assert result.remediation_required is True
    assert result.remediation_action_available is True
    assert result.commander_action_required is False


def test_assessor_allows_established_no_action():
    result = CommanderIntentAssessor().assess(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_required=False,
        remediation_action_available=False,
        commander_action_required=False,
    )

    assert result.remediation_required is False
    assert result.commander_action_required is False


def test_assessor_allows_commander_required():
    result = CommanderIntentAssessor().assess(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_required=True,
        remediation_action_available=False,
        commander_action_required=True,
    )

    assert result.commander_action_required is True


def test_empty_catalog_does_not_define_semantic_need():
    result = CommanderIntentAssessor().assess(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_required=False,
        remediation_action_available=False,
        commander_action_required=False,
    )

    assert result.remediation_required is False
    assert result.commander_action_required is False
