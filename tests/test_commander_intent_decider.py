from sentinel.commander_intent import CommanderIntent
from sentinel.commander_intent_decider import CommanderIntentDecider
from sentinel.diagnostic.models import DiagnosisStatus


def test_insufficient_evidence_has_highest_precedence():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
        remediation_action_available=True,
        commander_action_required=True,
    )

    assert result.intent is CommanderIntent.INSUFFICIENT_EVIDENCE
    assert result.reason


def test_need_commander_is_selected_when_intervention_is_required():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        commander_action_required=True,
        remediation_action_available=True,
    )

    assert result.intent is CommanderIntent.NEED_COMMANDER
    assert result.reason


def test_autonomous_remediate_requires_available_action():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_action_available=True,
    )

    assert result.intent is CommanderIntent.AUTONOMOUS_REMEDIATE
    assert result.reason


def test_established_diagnosis_without_action_is_no_action():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
    )

    assert result.intent is CommanderIntent.NO_ACTION
    assert result.reason


def test_insufficient_evidence_cannot_be_overridden_by_remediation():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.INSUFFICIENT_EVIDENCE,
        remediation_action_available=True,
    )

    assert result.intent is CommanderIntent.INSUFFICIENT_EVIDENCE


def test_commander_requirement_takes_precedence_over_autonomous_remediation():
    result = CommanderIntentDecider().decide(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_action_available=True,
        commander_action_required=True,
    )

    assert result.intent is CommanderIntent.NEED_COMMANDER


def test_intent_values_are_canonical():
    assert {item.value for item in CommanderIntent} == {
        "NO_ACTION",
        "AUTONOMOUS_REMEDIATE",
        "NEED_COMMANDER",
        "INSUFFICIENT_EVIDENCE",
    }


def test_intent_decider_has_no_execution_authority():
    public_api = {
        name
        for name in dir(CommanderIntentDecider)
        if not name.startswith("_")
    }

    assert public_api == {"decide"}
