"""Lane 1 regression tests for TMUX pane-title identity ingestion."""

from sentinel.normalization.resolver import (
    IdentityResolver,
    normalize_observations,
)
from sentinel.sensors.tmux.parser import TmuxStateParserV11


SOCKET = "/tmp/tmux-1000/default"
GENERATION = "uid=1000;pid=321;start=654"
CANONICAL_12_FIELD_LINE = (
    "$1\tairiv\t@1\t0\tunmapped-window\t0\t%1\t"
    "1\t0\tworker-pane\tbash\t100\n"
)
PREVIOUS_11_FIELD_LINE = (
    "$1\tairiv\t@1\t0\tunmapped-window\t0\t%1\t"
    "1\t0\tbash\t100\n"
)
LEGACY_9_FIELD_LINE = (
    "airiv\t0\tunmapped-window\t0\t%1\t"
    "1\t0\tbash\t100\n"
)


def configure_parser(parser, monkeypatch, pane_line):
    monkeypatch.setattr(
        parser,
        "_list_panes",
        lambda *, server_socket=None: pane_line,
    )
    monkeypatch.setattr(
        parser,
        "_resolve_server_identity",
        lambda: (SOCKET, GENERATION),
    )
    monkeypatch.setattr(
        parser,
        "capture_pane_content",
        lambda pane_id, *, server_socket=None: "steady-output",
    )
    monkeypatch.setattr(
        parser,
        "_server_generation_matches",
        lambda socket, generation: True,
    )


def test_list_panes_requests_pane_title_from_tmux(monkeypatch):
    parser = TmuxStateParserV11()
    calls = []

    def run(args, timeout=10, *, server_socket=None):
        calls.append((args, server_socket))
        return ""

    monkeypatch.setattr(parser, "_run_tmux_cmd", run)

    parser._list_panes(server_socket=SOCKET)

    args, socket = calls[0]
    assert socket == SOCKET
    assert args[:5] == ["list-panes", "-a", "-t", "airiv", "-F"]
    format_str = args[5]
    assert "#{pane_title}" in format_str
    assert "#{pane_dead}\t#{pane_title}\t#{pane_current_command}" in format_str


def test_canonical_tmux_pane_title_reaches_identity_resolver(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(parser, monkeypatch, CANONICAL_12_FIELD_LINE)

    raw = parser.inspect_panes()

    assert len(raw) == 1
    assert raw[0]["pane_title"] == "worker-pane"
    assert raw[0]["window_name"] == "unmapped-window"
    assert raw[0]["tmux_identity_valid"] is True

    normalized = normalize_observations(
        raw,
        IdentityResolver({"worker-pane": "AGENT_FROM_PANE_TITLE"}),
    )

    assert normalized[0]["agent_identity"] == "AGENT_FROM_PANE_TITLE"


def test_previous_11_field_record_remains_backward_compatible(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(parser, monkeypatch, PREVIOUS_11_FIELD_LINE)

    observation = parser.inspect_panes()[0]

    assert observation["pane_title"] is None
    assert observation["current_command"] == "bash"
    assert observation["pane_pid"] == 100
    assert observation["tmux_identity_valid"] is True


def test_legacy_9_field_record_remains_backward_compatible(monkeypatch):
    parser = TmuxStateParserV11()
    configure_parser(parser, monkeypatch, LEGACY_9_FIELD_LINE)

    observation = parser.inspect_panes()[0]

    assert observation["pane_title"] is None
    assert observation["session_id"] is None
    assert observation["window_id"] is None
    assert observation["current_command"] == "bash"
    assert observation["pane_pid"] == 100
    assert observation["tmux_identity_valid"] is False
