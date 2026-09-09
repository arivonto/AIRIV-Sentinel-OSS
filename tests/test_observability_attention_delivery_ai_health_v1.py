import ast
from dataclasses import FrozenInstanceError

import pytest

from sentinel.worker.attention_health import (
    AIExecutionHealthProjection,
    CommanderAttentionProjection,
    DeliveryHealthProjection,
    project_ai_execution_health,
    project_commander_attention,
    project_delivery_health,
)


def test_commander_attention_projection_is_explicit_ordered_and_immutable():
    projection = project_commander_attention([
        {"attention_id": "A-1", "requires_attention": True, "resolved": False},
        {"attention_id": "A-2", "requires_attention": True, "resolved": True},
        {"attention_id": "A-3", "requires_attention": True, "resolved": False},
        {"attention_id": "A-4", "requires_attention": None, "resolved": False},
    ])

    assert projection == CommanderAttentionProjection(
        total_items=4,
        pending_count=2,
        resolved_count=1,
        unknown_count=1,
        pending_ids=("A-1", "A-3"),
    )
    with pytest.raises(FrozenInstanceError):
        projection.pending_count = 99


def test_delivery_health_preserves_failure_unknown_and_duplicate_identity():
    projection = project_delivery_health([
        {"delivery_id": "D-1", "status": "DELIVERED"},
        {"delivery_id": "D-2", "status": "PENDING"},
        {"delivery_id": "D-3", "status": "FAILED"},
        {"delivery_id": "D-3", "status": "DELIVERED"},
        {"delivery_id": "", "status": "UNKNOWN_VALUE"},
    ])

    assert projection == DeliveryHealthProjection(
        total_records=5,
        pending_count=1,
        delivered_count=2,
        failed_count=1,
        unknown_count=2,
        duplicate_identity_count=1,
        health="DEGRADED",
    )


def test_ai_health_requires_explicit_identity_and_verification_success():
    projection = project_ai_execution_health([
        {"execution_id": "E-1", "identity_status": "PRESENT", "verification_status": "VERIFIED"},
        {"execution_id": "E-2", "identity_status": "MISSING", "verification_status": "VERIFIED"},
        {"execution_id": "E-3", "identity_status": "PRESENT", "verification_status": "FAILED"},
        {"execution_id": "E-3", "identity_status": "UNKNOWN", "verification_status": "UNKNOWN"},
    ])

    assert projection == AIExecutionHealthProjection(
        total_records=4,
        healthy_count=1,
        identity_missing_count=1,
        verification_failed_count=1,
        unknown_count=1,
        duplicate_execution_id_count=1,
        health="DEGRADED",
    )


def test_empty_inputs_are_deterministic_and_side_effect_free():
    assert project_commander_attention([]) == CommanderAttentionProjection(0, 0, 0, 0, ())
    assert project_delivery_health([]) == DeliveryHealthProjection(0, 0, 0, 0, 0, 0, "HEALTHY")
    assert project_ai_execution_health([]) == AIExecutionHealthProjection(0, 0, 0, 0, 0, 0, "HEALTHY")


def test_projection_module_has_only_passive_standard_library_dependencies():
    from sentinel.worker import attention_health

    tree = ast.parse(open(attention_health.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported <= {"dataclasses", "typing"}


def test_identical_inputs_produce_identical_projections():
    records = (
        {"delivery_id": "D-1", "status": "DELIVERED"},
        {"delivery_id": "D-2", "status": "PENDING"},
    )
    assert project_delivery_health(records) == project_delivery_health(records)
