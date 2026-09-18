import subprocess

from sentinel.mission_workspace import observe_workspace


def test_workspace_observation_reads_git_facts_without_mutation():
    before = subprocess.run(
        ("git", "status", "--porcelain"),
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    observation = observe_workspace(".")

    after = subprocess.run(
        ("git", "status", "--porcelain"),
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    assert observation.git_available is True
    assert observation.branch
    assert len(observation.head_sha) == 40
    assert len(observation.origin_main_sha) == 40
    assert observation.to_evidence()["git_available"] is True
    assert before == after
