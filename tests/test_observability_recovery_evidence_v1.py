import ast
from dataclasses import FrozenInstanceError

import pytest

from sentinel.worker.recovery_evidence import (
    RecoveryEvidenceHealth,
    RecoveryEvidenceProjection,
    RecoveryEvidenceStatus,
    RecoveryScenarioProjection,
    project_recovery_evidence,
)


def _scenario(**overrides):
    record = {
        "scenario_id": "REC-1",
        "failure_class": "WORKER_UNHEALTHY",
        "injection_scope": "SYNTHETIC",
        "before_state": "HEALTHY",
        "failure_state": "UNHEALTHY",
        "after_state": "HEALTHY",
        "expected_recovery_state": "HEALTHY",
        "verification_status": "VERIFIED",
        "effect_attempted": False,
    }
    record.update(overrides)
    return record


def test_verified_synthetic_recovery_is_healthy():
    projection = project_recovery_evidence([_scenario()])

    assert projection == RecoveryEvidenceProjection(
        total_records=1,
        recovered_count=1,
        not_recovered_count=0,
        unknown_count=0,
        duplicate_scenario_id_count=0,
        scope_violation_count=0,
        effect_attempt_violation_count=0,
        health=RecoveryEvidenceHealth.HEALTHY,
        scenarios=(
            RecoveryScenarioProjection(
                scenario_id="REC-1",
                failure_class="WORKER_UNHEALTHY",
                injection_scope="SYNTHETIC",
                before_state="HEALTHY",
                failure_state="UNHEALTHY",
                after_state="HEALTHY",
                expected_recovery_state="HEALTHY",
                verification_status="VERIFIED",
                status=RecoveryEvidenceStatus.RECOVERED,
                duplicate_identity=False,
                scope_violation=False,
                effect_attempt_violation=False,
            ),
        ),
    )


def test_verified_state_mismatch_is_not_recovered():
    projection = project_recovery_evidence([
        _scenario(after_state="DEGRADED", expected_recovery_state="HEALTHY"),
    ])

    assert projection.not_recovered_count == 1
    assert projection.unknown_count == 0
    assert projection.scenarios[0].status is RecoveryEvidenceStatus.NOT_RECOVERED
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_explicit_verification_failure_is_not_recovered():
    projection = project_recovery_evidence([
        _scenario(verification_status="FAILED"),
    ])

    assert projection.not_recovered_count == 1
    assert projection.scenarios[0].status is RecoveryEvidenceStatus.NOT_RECOVERED
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_unknown_verification_never_becomes_recovery_success():
    projection = project_recovery_evidence([
        _scenario(verification_status="UNKNOWN"),
    ])

    assert projection.recovered_count == 0
    assert projection.unknown_count == 1
    assert projection.scenarios[0].status is RecoveryEvidenceStatus.UNKNOWN
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_missing_effect_attempt_fact_is_unknown_not_success():
    record = _scenario()
    del record["effect_attempted"]
    projection = project_recovery_evidence([record])

    assert projection.recovered_count == 0
    assert projection.unknown_count == 1
    assert projection.effect_attempt_violation_count == 0


def test_failure_must_be_observed_as_distinct_from_before_state():
    projection = project_recovery_evidence([
        _scenario(failure_state="HEALTHY"),
    ])

    assert projection.recovered_count == 0
    assert projection.unknown_count == 1
    assert projection.scenarios[0].status is RecoveryEvidenceStatus.UNKNOWN


def test_production_scope_is_integrity_violation_and_unknown():
    projection = project_recovery_evidence([
        _scenario(injection_scope="PRODUCTION"),
    ])

    assert projection.recovered_count == 0
    assert projection.unknown_count == 1
    assert projection.scope_violation_count == 1
    assert projection.scenarios[0].scope_violation is True
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_effect_attempt_is_integrity_violation_and_unknown():
    projection = project_recovery_evidence([
        _scenario(effect_attempted=True),
    ])

    assert projection.recovered_count == 0
    assert projection.unknown_count == 1
    assert projection.effect_attempt_violation_count == 1
    assert projection.scenarios[0].effect_attempt_violation is True
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_duplicate_scenario_identity_degrades_and_prevents_success():
    projection = project_recovery_evidence([
        _scenario(),
        _scenario(after_state="HEALTHY"),
    ])

    assert projection.duplicate_scenario_id_count == 1
    assert projection.recovered_count == 0
    assert projection.unknown_count == 2
    assert all(item.duplicate_identity for item in projection.scenarios)
    assert projection.health is RecoveryEvidenceHealth.DEGRADED


def test_malformed_symbolic_metadata_remains_unknown():
    projection = project_recovery_evidence([
        _scenario(failure_class="contains spaces and raw payload"),
    ])

    assert projection.scenarios[0].failure_class is None
    assert projection.unknown_count == 1
    assert projection.recovered_count == 0


def test_non_production_scope_is_foundation_eligible():
    projection = project_recovery_evidence([
        _scenario(injection_scope="NON_PRODUCTION"),
    ])

    assert projection.recovered_count == 1
    assert projection.scope_violation_count == 0
    assert projection.health is RecoveryEvidenceHealth.HEALTHY


def test_empty_observation_set_is_unknown_not_synthetic_success():
    assert project_recovery_evidence([]) == RecoveryEvidenceProjection(
        total_records=0,
        recovered_count=0,
        not_recovered_count=0,
        unknown_count=0,
        duplicate_scenario_id_count=0,
        scope_violation_count=0,
        effect_attempt_violation_count=0,
        health=RecoveryEvidenceHealth.UNKNOWN,
        scenarios=(),
    )


def test_projection_preserves_input_order_is_deterministic_and_immutable():
    records = (
        _scenario(scenario_id="REC-2"),
        _scenario(scenario_id="REC-1", verification_status="FAILED"),
    )
    projection = project_recovery_evidence(records)

    assert projection == project_recovery_evidence(records)
    assert tuple(item.scenario_id for item in projection.scenarios) == ("REC-2", "REC-1")
    with pytest.raises(FrozenInstanceError):
        projection.recovered_count = 99
    with pytest.raises(FrozenInstanceError):
        projection.scenarios[0].status = RecoveryEvidenceStatus.UNKNOWN


def test_module_has_only_passive_standard_library_dependencies_and_no_injector():
    from sentinel.worker import recovery_evidence

    tree = ast.parse(open(recovery_evidence.__file__, encoding="utf-8").read())
    imported = set()
    function_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.FunctionDef):
            function_names.add(node.name)

    assert imported <= {"dataclasses", "enum", "typing"}
    assert not any(
        name.startswith(("inject", "execute", "restart", "rollback", "remediate"))
        for name in function_names
    )


def test_projection_states_cannot_be_used_as_boolean_authority():
    assert RecoveryEvidenceHealth.HEALTHY != True
    assert RecoveryEvidenceHealth.DEGRADED != False
    assert RecoveryEvidenceStatus.RECOVERED != True
    assert RecoveryEvidenceStatus.NOT_RECOVERED != False
