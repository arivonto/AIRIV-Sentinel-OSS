"""Shared Web/Desktop Commander surface projection tests."""

import ast
from pathlib import Path

import pytest

from sentinel.commander_surface import (
    CommanderSurfaceFacts,
    SurfaceStatus,
    load_commander_surface_payload,
    project_commander_surface,
)


def facts(**changes):
    values = dict(
        snapshot_id="snap-20260913-001",
        observed_at="2026-09-13T09:00:00+07:00",
        service_unit="airiv-sentinel.service",
        service_state="active/running",
        runtime_identity="runtime-main-e8d9648",
        readiness_state="READY",
        active_incidents=0,
        evidence_complete=True,
    )
    values.update(changes)
    return CommanderSurfaceFacts(**values)


def test_ready_projection_is_read_only_and_effect_free():
    projection = project_commander_surface(facts())

    assert projection.status is SurfaceStatus.READY
    assert projection.reason == "read_only_surface_ready"
    assert projection.read_only is True
    assert projection.production_effect == "NONE"


def test_payload_is_stable_and_contains_no_authority_fields():
    payload = project_commander_surface(facts()).to_payload()

    assert payload == {
        "schema": "airiv.sentinel.commander_surface.v1",
        "status": "READY",
        "reason": "read_only_surface_ready",
        "headline": "Evidence surface ready",
        "read_only": True,
        "production_effect": "NONE",
        "facts": {
            "snapshot_id": "snap-20260913-001",
            "observed_at": "2026-09-13T09:00:00+07:00",
            "service_unit": "airiv-sentinel.service",
            "service_state": "active/running",
            "runtime_identity": "runtime-main-e8d9648",
            "readiness_state": "READY",
            "active_incidents": 0,
            "evidence_complete": True,
            "production_effect": "NONE",
        },
    }
    assert not {"command", "authorization", "action", "endpoint"} & set(payload)


def test_payload_round_trip_is_safe_for_surface_consumers():
    projection = project_commander_surface(facts())

    loaded = load_commander_surface_payload(projection.to_payload())

    assert loaded == projection


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(status="BLOCKED"),
        lambda value: value.update(read_only=False),
        lambda value: value.update(production_effect="RESTART"),
        lambda value: value["facts"].update(active_incidents=-1),
        lambda value: value.update(command="restart"),
    ],
)
def test_payload_tampering_fails_closed(mutate):
    payload = project_commander_surface(facts()).to_payload()
    mutate(payload)

    with pytest.raises((TypeError, ValueError)):
        load_commander_surface_payload(payload)


@pytest.mark.parametrize(
    ("changes", "status", "reason"),
    [
        ({"readiness_state": "ACTIVATION_BLOCKED"}, SurfaceStatus.BLOCKED, "activation_remains_blocked"),
        ({"service_state": "inactive"}, SurfaceStatus.BLOCKED, "runtime_or_evidence_not_ready"),
        ({"evidence_complete": False}, SurfaceStatus.BLOCKED, "runtime_or_evidence_not_ready"),
        ({"readiness_state": "UNKNOWN"}, SurfaceStatus.UNKNOWN, "surface_facts_incomplete"),
        ({"service_state": "unknown"}, SurfaceStatus.UNKNOWN, "surface_facts_incomplete"),
    ],
)
def test_projection_fails_closed(changes, status, reason):
    projection = project_commander_surface(facts(**changes))

    assert projection.status is status
    assert projection.reason == reason
    assert projection.read_only is True
    assert projection.production_effect == "NONE"


@pytest.mark.parametrize(
    "changes",
    [
        {"service_unit": "other.service"},
        {"active_incidents": -1},
        {"evidence_complete": 1},
        {"production_effect": "RESTART"},
        {"snapshot_id": "invalid id"},
    ],
)
def test_facts_reject_invalid_shapes(changes):
    with pytest.raises(ValueError):
        facts(**changes)


def test_projection_rejects_other_types():
    with pytest.raises(TypeError):
        project_commander_surface(object())


def test_module_has_no_effect_authority_or_host_io():
    source = Path("sentinel/commander_surface.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "subprocess", "systemctl", "sudo", "pkexec", "socket", "requests",
        "restart", "stop", "start", "execute", "resolve", "open",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert not (names | attributes) & forbidden
