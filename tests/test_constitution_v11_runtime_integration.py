"""AIRIV Sentinel constitution v1.1 runtime integration."""

from sentinel.constitution import (
    V11_AUTHENTICITY_MODE,
    V11_AUTHORITY_PROFILE,
    V11_PRODUCTION_MODE,
    V11_STATUS,
    V11_VERSION,
    load_active_constitution,
)
from sentinel.engineering_autonomy import (
    EngineeringDecision,
    classify_engineering_request,
)
from sentinel.runtime import SentinelRuntime


def test_active_constitution_v11_is_loaded_from_repository():
    constitution = load_active_constitution()

    assert constitution.version == V11_VERSION
    assert constitution.status == V11_STATUS
    assert constitution.authority_profile == V11_AUTHORITY_PROFILE
    assert constitution.authenticity_mode == V11_AUTHENTICITY_MODE
    assert constitution.routine_development_approval_required is False
    assert constitution.production_mode == V11_PRODUCTION_MODE
    assert constitution.blueprint_digest_verified is True
    assert constitution.v11_runtime_active is True


def test_runtime_startup_exposes_constitution_v11_facts():
    runtime = SentinelRuntime()

    assert runtime.constitution.v11_runtime_active is True
    assert runtime.authority_profile == V11_AUTHORITY_PROFILE
    assert runtime.authenticity_mode == V11_AUTHENTICITY_MODE
    assert runtime.routine_development_approval_required is False
    assert runtime.production_mode == V11_PRODUCTION_MODE
    assert runtime.policy.list_systemd_production_targets() == ()


def test_trusted_engineering_routine_work_does_not_require_approval():
    record = classify_engineering_request(
        {
            "decision_id": "V11-DEV-1",
            "request_identity": "local-main",
            "operation": "local_shell_execution",
            "authority_basis": "constitution-v1.1",
            "authority_profile": V11_AUTHORITY_PROFILE,
        }
    )

    assert record.decision is EngineeringDecision.ALLOWED
    assert record.production_effect == "NONE"
    assert record.reason == "routine development operation is allowed by constitution v1.1"


def test_production_and_constitution_boundaries_remain_separately_bounded():
    production = classify_engineering_request(
        {
            "decision_id": "V11-PROD-1",
            "request_identity": "local-main",
            "operation": "production_restart",
            "authority_basis": "constitution-v1.1",
            "authority_profile": V11_AUTHORITY_PROFILE,
        }
    )
    constitutional = classify_engineering_request(
        {
            "decision_id": "V11-CONST-1",
            "request_identity": "local-main",
            "operation": "contract_amendment",
            "authority_basis": "constitution-v1.1",
            "authority_profile": V11_AUTHORITY_PROFILE,
        }
    )

    assert production.decision is EngineeringDecision.ESCALATE
    assert constitutional.decision is EngineeringDecision.ESCALATE
