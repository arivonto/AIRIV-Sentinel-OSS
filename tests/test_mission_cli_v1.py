from io import StringIO
import runpy
import sys

import pytest

from sentinel import mission_cli


def test_mission_cli_runs_blueprint_definition_of_success_command():
    stdout = StringIO()

    code = mission_cli.main(
        ["mission", "Fix this repository until all tests pass."],
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert code == 0
    assert "MISSION_STATUS=COMPLETE" in output
    assert "MISSION_ACCEPTED=YES" in output
    assert "MISSION_EFFECT=NONE" in output
    assert "MISSION_EVENT_COUNT=8" in output
    assert "MISSION_WORKSPACE_GIT=YES" in output
    assert "MISSION_WORKSPACE_HEAD=" in output
    assert "MISSION_WORKSPACE_BRANCH=" in output
    for stage in (
        "observe",
        "understand",
        "plan",
        "execute",
        "verify",
        "retry",
        "complete",
        "learn",
    ):
        assert f"MISSION_STAGE={stage}" in output


def test_mission_cli_rejects_missing_objective():
    stdout = StringIO()

    assert mission_cli.main(["mission"], stdout=stdout) == 2
    assert "usage: sentinel mission" in stdout.getvalue()


def test_main_module_routes_mission_without_starting_daemon(monkeypatch):
    daemon_main = pytest.fail
    stdout = StringIO()

    monkeypatch.setattr("sentinel.__main__.main", daemon_main)
    monkeypatch.setattr(sys, "argv", [
        "python -m sentinel",
        "mission",
        "Fix this repository until all tests pass.",
    ])
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.delitem(sys.modules, "sentinel.__main__", raising=False)

    with pytest.raises(SystemExit) as caught:
        runpy.run_module("sentinel.__main__", run_name="__main__")

    assert caught.value.code == 0
    assert "MISSION_STATUS=COMPLETE" in stdout.getvalue()
