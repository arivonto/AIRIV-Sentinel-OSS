import ast
from dataclasses import FrozenInstanceError

import pytest

from sentinel.worker.release_health import (
    ArtifactValidationHealthProjection,
    PostUpgradeVerificationHealthProjection,
    ProjectionHealth,
    ReleaseReadinessHealthProjection,
    RestartUpgradeContinuityHealthProjection,
    project_artifact_validation_health,
    project_post_upgrade_verification_health,
    project_release_readiness,
    project_restart_upgrade_continuity_health,
)


def test_release_readiness_projection_preserves_not_ready_unknown_and_duplicates():
    projection = project_release_readiness([
        {"release_id": "R-1", "status": "READY"},
        {"release_id": "R-2", "status": "NOT_READY"},
        {"release_id": "R-2", "status": "READY"},
        {"release_id": "", "status": "OTHER"},
    ])

    assert projection == ReleaseReadinessHealthProjection(
        total_records=4,
        ready_count=2,
        not_ready_count=1,
        unknown_record_count=1,
        duplicate_release_id_count=1,
        health=ProjectionHealth.DEGRADED,
    )


def test_artifact_validation_projection_preserves_rejection_and_unknown():
    projection = project_artifact_validation_health([
        {"artifact_id": "A-1", "status": "VERIFIED"},
        {"artifact_id": "A-2", "status": "REJECTED"},
        {"artifact_id": "A-2", "status": "VERIFIED"},
        {"artifact_id": None, "status": "UNKNOWN"},
    ])

    assert projection == ArtifactValidationHealthProjection(
        total_records=4,
        verified_count=2,
        rejected_count=1,
        unknown_record_count=1,
        duplicate_artifact_id_count=1,
        health=ProjectionHealth.DEGRADED,
    )


def test_post_upgrade_projection_detects_failure_unknown_duplicate_and_authority_violation():
    projection = project_post_upgrade_verification_health([
        {"verification_id": "V-1", "status": "VERIFIED", "rollback_authorized": False},
        {"verification_id": "V-2", "status": "FAILED", "rollback_authorized": False},
        {"verification_id": "V-3", "status": "UNKNOWN", "rollback_authorized": False},
        {"verification_id": "V-3", "status": "VERIFIED", "rollback_authorized": True},
    ])

    assert projection == PostUpgradeVerificationHealthProjection(
        total_records=4,
        verified_count=2,
        failed_count=1,
        unknown_record_count=1,
        duplicate_verification_id_count=1,
        rollback_authority_violation_count=1,
        health=ProjectionHealth.DEGRADED,
    )


def test_post_upgrade_missing_rollback_authorization_is_unknown_not_success():
    projection = project_post_upgrade_verification_health([
        {"verification_id": "V-1", "status": "VERIFIED"},
    ])

    assert projection.verified_count == 1
    assert projection.unknown_record_count == 1
    assert projection.rollback_authority_violation_count == 0
    assert projection.health is ProjectionHealth.DEGRADED


def test_explicit_successful_observations_are_healthy():
    assert project_release_readiness([
        {"release_id": "R-1", "status": "READY"},
    ]).health is ProjectionHealth.HEALTHY
    assert project_artifact_validation_health([
        {"artifact_id": "A-1", "status": "VERIFIED"},
    ]).health is ProjectionHealth.HEALTHY
    assert project_post_upgrade_verification_health([
        {"verification_id": "V-1", "status": "VERIFIED", "rollback_authorized": False},
    ]).health is ProjectionHealth.HEALTHY


def test_empty_observation_sets_are_unknown_not_synthetic_success():
    assert project_release_readiness([]) == ReleaseReadinessHealthProjection(
        0, 0, 0, 0, 0, ProjectionHealth.UNKNOWN
    )
    assert project_artifact_validation_health([]) == ArtifactValidationHealthProjection(
        0, 0, 0, 0, 0, ProjectionHealth.UNKNOWN
    )
    assert project_post_upgrade_verification_health([]) == PostUpgradeVerificationHealthProjection(
        0, 0, 0, 0, 0, 0, ProjectionHealth.UNKNOWN
    )
    assert project_restart_upgrade_continuity_health([]) == RestartUpgradeContinuityHealthProjection(
        0, 0, 0, 0, 0, 0, ProjectionHealth.UNKNOWN
    )


def test_restart_upgrade_continuity_projection_preserves_continuous_observations():
    projection = project_restart_upgrade_continuity_health([
        {
            "observation_id": "C-1",
            "before_identity": "runtime@abc",
            "after_identity": "runtime@abc",
            "continuity_status": "CONTINUOUS",
            "effect_authorized": False,
        },
    ])

    assert projection == RestartUpgradeContinuityHealthProjection(
        total_records=1,
        continuous_count=1,
        changed_count=0,
        unknown_record_count=0,
        duplicate_observation_id_count=0,
        authority_violation_count=0,
        health=ProjectionHealth.HEALTHY,
    )


def test_restart_upgrade_continuity_projection_preserves_change_unknown_and_duplicates():
    projection = project_restart_upgrade_continuity_health([
        {
            "observation_id": "C-1",
            "before_identity": "runtime@abc",
            "after_identity": "runtime@def",
            "continuity_status": "CHANGED",
            "effect_authorized": False,
        },
        {
            "observation_id": "C-1",
            "before_identity": "runtime@abc",
            "after_identity": "runtime@abc",
            "continuity_status": "CONTINUOUS",
            "effect_authorized": False,
        },
        {
            "observation_id": "C-3",
            "before_identity": "",
            "after_identity": "runtime@ghi",
            "continuity_status": "UNKNOWN",
            "effect_authorized": False,
        },
    ])

    assert projection == RestartUpgradeContinuityHealthProjection(
        total_records=3,
        continuous_count=1,
        changed_count=1,
        unknown_record_count=1,
        duplicate_observation_id_count=1,
        authority_violation_count=0,
        health=ProjectionHealth.DEGRADED,
    )


def test_restart_upgrade_continuity_projection_rejects_authority_and_conflict_as_health():
    projection = project_restart_upgrade_continuity_health([
        {
            "observation_id": "C-1",
            "before_identity": "runtime@abc",
            "after_identity": "runtime@def",
            "continuity_status": "CONTINUOUS",
            "effect_authorized": True,
        },
    ])

    assert projection.changed_count == 1
    assert projection.unknown_record_count == 1
    assert projection.authority_violation_count == 1
    assert projection.health is ProjectionHealth.DEGRADED


def test_projection_outputs_are_immutable_and_deterministic():
    records = ({"release_id": "R-1", "status": "READY"},)
    projection = project_release_readiness(records)
    assert projection == project_release_readiness(records)
    with pytest.raises(FrozenInstanceError):
        projection.ready_count = 99


def test_projection_module_has_only_passive_standard_library_dependencies():
    from sentinel.worker import release_health

    tree = ast.parse(open(release_health.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported <= {"dataclasses", "enum", "typing"}


def test_health_values_cannot_be_used_as_boolean_authority():
    assert ProjectionHealth.HEALTHY != True
    assert ProjectionHealth.DEGRADED != False
