"""Static safety checks for the read-only Commander Web consumer."""

from pathlib import Path


INDEX = Path("index.html")


def test_web_console_exposes_local_payload_loader_and_boundary():
    source = INDEX.read_text(encoding="utf-8")

    for marker in (
        'id="web-console"',
        'id="payload-file"',
        'id="payload-load-status"',
        'id="payload-rendered-facts"',
        "airiv.sentinel.commander_surface.v1",
        "Payload accepted: read-only v1",
        "Payload rejected: schema or authority boundary mismatch",
        "No evidence rendered because the payload failed validation.",
    ):
        assert marker in source


def test_web_payload_loader_has_no_network_or_host_control_path():
    source = INDEX.read_text(encoding="utf-8")

    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "WebSocket",
        "systemctl",
        "subprocess",
        "window.location",
    ):
        assert forbidden not in source
