from sentinel.commander_intent_assessment import (
    CommanderIntentAssessment,
)
from sentinel.diagnostic.models import DiagnosisStatus


def test_assessment_is_pure_semantic_fact_container():
    fields = set(
        CommanderIntentAssessment.__dataclass_fields__
    )

    assert fields == {
        "diagnosis_status",
        "remediation_required",
        "remediation_action_available",
        "commander_action_required",
        "semantic_configured",
        "semantic_reason",
    }


def test_assessment_does_not_import_diagnostic_runtime():
    import sys

    module_name = (
        "sentinel.commander_intent_assessment"
    )

    assert module_name in sys.modules

    module = sys.modules[module_name]

    assert not hasattr(
        module,
        "RuntimeDiagnosticCoordinator",
    )


def test_boolean_fact_types_are_enforced():
    assessment = CommanderIntentAssessment(
        diagnosis_status=DiagnosisStatus.ESTABLISHED,
        remediation_required=True,
        remediation_action_available=True,
        commander_action_required=False,
    )

    assert assessment.remediation_required is True
    assert assessment.remediation_action_available is True
    assert assessment.commander_action_required is False
