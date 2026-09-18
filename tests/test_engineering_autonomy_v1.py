from sentinel.engineering_autonomy import (
    EngineeringDecision,
    EngineeringDecisionRecord,
    classify_engineering_request,
)


def request(**overrides):
    value = {
        "decision_id": "DEC-1",
        "request_identity": "PR-45@0bf36e8",
        "operation": "run_tests",
        "authority_basis": "bounded-autonomy-v1",
    }
    value.update(overrides)
    return value


def test_safe_engineering_request_is_allowed_without_effect_authority():
    record = classify_engineering_request(request())
    assert record == EngineeringDecisionRecord(
        decision_id="DEC-1",
        request_identity="PR-45@0bf36e8",
        decision=EngineeringDecision.ALLOWED,
        authority_basis="bounded-autonomy-v1",
        reason="bounded engineering operation is within the approved foundation",
    )
    assert record.production_effect == "NONE"


def test_production_and_authority_operations_fail_closed():
    assert classify_engineering_request(request(operation="production_restart")).decision is EngineeringDecision.ESCALATE
    assert classify_engineering_request(request(operation="provider_live")).decision is EngineeringDecision.DENIED
    assert classify_engineering_request(request(operation="new_operation")).decision is EngineeringDecision.UNKNOWN


def test_constitution_v11_allows_routine_development_shell_without_production_effect():
    record = classify_engineering_request(
        request(
            operation="local_shell_execution",
            authority_basis="constitution-v1.1",
            authority_profile="TRUSTED_AUTONOMOUS_ENGINEERING",
        )
    )

    assert record.decision is EngineeringDecision.ALLOWED
    assert record.production_effect == "NONE"


def test_missing_facts_are_unknown():
    record = classify_engineering_request({"operation": "run_tests"})
    assert record.decision is EngineeringDecision.UNKNOWN
    assert record.production_effect == "NONE"
