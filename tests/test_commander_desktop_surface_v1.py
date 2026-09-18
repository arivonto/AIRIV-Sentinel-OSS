"""Toolkit-neutral Desktop Commander consumer tests."""

import ast
from pathlib import Path

import pytest

from sentinel.commander_desktop_surface import CommanderDesktopView
from sentinel.commander_surface import SurfaceStatus


def payload(**changes):
    value = {
        "schema": "airiv.sentinel.commander_surface.v1",
        "status": "READY",
        "reason": "read_only_surface_ready",
        "headline": "Evidence surface ready",
        "read_only": True,
        "production_effect": "NONE",
        "facts": {
            "snapshot_id": "snap-desktop-001",
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
    value.update(changes)
    return value


def test_desktop_view_consumes_shared_payload_contract():
    view = CommanderDesktopView.from_payload(payload())

    assert view.status is SurfaceStatus.READY
    assert view.headline == "Evidence surface ready"
    assert view.snapshot_id == "snap-desktop-001"
    assert view.service_state == "active/running"
    assert view.read_only is True
    assert view.production_effect == "NONE"


def test_desktop_view_preserves_blocked_state():
    value = payload(
        status="BLOCKED",
        reason="activation_remains_blocked",
        headline="Activation blocked",
    )
    value["facts"]["readiness_state"] = "ACTIVATION_BLOCKED"

    assert CommanderDesktopView.from_payload(value).status is SurfaceStatus.BLOCKED


def test_desktop_view_rejects_invalid_payload():
    value = payload(production_effect="RESTART")

    with pytest.raises(ValueError):
        CommanderDesktopView.from_payload(value)


def test_desktop_module_has_no_effect_or_host_authority():
    source = Path("sentinel/commander_desktop_surface.py").read_text(encoding="utf-8")
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
