from io import StringIO

from sentinel import mission_cli


def test_mission_cli_rejects_missing_objective():
    stdout = StringIO()

    assert mission_cli.main(["mission"], stdout=stdout) == 2
    assert "usage: sentinel mission" in stdout.getvalue()
