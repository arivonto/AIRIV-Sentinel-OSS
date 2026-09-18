"""Regression locks for GitHub-hosted parallel-engineering CI mechanics."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOW_DIR / "ci.yml"
REQUIREMENTS = ROOT / "requirements-dev.txt"
REQUIREMENTS_LOCK = ROOT / "requirements-dev-lock.txt"
PINNED_ACTIONS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "634f93cb2916e3fdff6788551b99b062d0335ce0",
    "actions/create-github-app-token": "0d564482f06ca65fa9e77e2510873638c82206f2",
}


def _ci_text() -> str:
    return CI_WORKFLOW.read_text(encoding="utf-8")


def _workflow_files() -> list[Path]:
    return sorted(
        [
            *WORKFLOW_DIR.glob("*.yml"),
            *WORKFLOW_DIR.glob("*.yaml"),
        ]
    )


def test_parallel_ci_remains_github_hosted_and_read_only():
    """Routine branch/PR validation must not consume or trust the production host."""
    text = _ci_text()

    assert "runs-on: ubuntu-latest" in text
    assert "self-hosted" not in text
    assert "permissions:\n  contents: read" in text
    assert "systemctl" not in text
    assert "sudo " not in text
    assert "/home/arivonto" not in text
    assert "/var/lib/airiv-sentinel" not in text
    assert "/etc/airiv-sentinel" not in text


def test_parallel_ci_covers_engineering_branches_and_pull_requests():
    """Each lane receives canonical validation through its pull request."""
    text = _ci_text()

    assert "pull_request:" in text
    assert "branches: [main]" in text
    assert "fetch-depth: 0" in text
    assert "group: airiv-sentinel-ci-${{ github.event.pull_request.number || github.ref }}" in text
    assert "cancel-in-progress: true" in text


def test_parallel_ci_does_not_duplicate_pull_request_validation_on_lane_pushes():
    """Engineering lane pushes must not create duplicate PR checks."""
    text = _ci_text()

    assert "push:" in text
    assert "- main" in text
    assert "engineering/**" not in text


def test_parallel_ci_reserves_full_regression_for_pull_requests():
    """Main pushes keep fast gates while PRs retain the complete regression."""
    text = _ci_text()
    marker = "- name: Run full regression"
    full_regression = text.split(marker, 1)[1]

    assert "if: github.event_name == 'pull_request'" in full_regression


def test_parallel_ci_keeps_required_fail_closed_gates_visible():
    """Guard against CI-success caused by silently deleting a required validation gate."""
    text = _ci_text()
    required_markers = (
        "STALE_MAIN_GATE=PASS",
        "STALE_MAIN_FINAL_GATE=PASS",
        "PATCH_HYGIENE=PASS",
        "DEV_DEPENDENCY_MANIFEST=PASS",
        "PIP_BOOTSTRAP_CONTRACT=PASS",
        "DEV_DEPENDENCY_LOCK=PASS",
        "TEST_DISCOVERY_INTEGRITY=PASS",
        "DISCLOSURE_GATE=PASS",
        "HOST_ISOLATION=PASS",
        "COMMANDER_DISCOVERY=PASS",
        "COMMANDER_BOUNDARY=PASS",
        "SECURITY_GATES=PASS",
        "CI_SELF_TEST=PASS",
    )

    for marker in required_markers:
        assert marker in text, f"CI gate marker missing: {marker}"

    assert "python -m pytest --collect-only" in text
    assert "python -m pytest -q -p no:cacheprovider" in text
    assert "scripts/public_release_secret_scan.sh" in text
    assert "scripts/validate_project_docs.py" in text


def test_pytest_discovery_uses_recursive_git_tracked_modules():
    """Nested tracked tests must not escape the required-test discovery contract."""
    text = _ci_text()

    # Dual-root discovery: canonical CI collects tracked modules from BOTH
    # tests/ and canonical_tests/ (the public export keeps this invocation;
    # its unmatched canonical_tests pathspec lists nothing).
    assert '["git", "ls-files", "-z", "--", "tests", "canonical_tests"]' in text
    assert 'Path("tests").glob("test_*.py")' not in text
    assert 'Path(path).name.startswith("test_")' in text
    assert 'Path(path).suffix == ".py"' in text
    assert "MISSING_COLLECTED_TEST_MODULE=" in text


def test_parallel_ci_revalidates_current_main_before_acceptance():
    """A main update during a long run must invalidate final CI acceptance."""
    text = _ci_text()
    marker = "- name: Revalidate main and report Lane 5 CI acceptance"

    assert marker in text
    final_gate = text.split(marker, 1)[1]
    assert "git fetch --no-tags origin main" in final_gate
    assert 'FINAL_MAIN_SHA="$(git rev-parse origin/main)"' in final_gate
    assert 'git merge-base --is-ancestor "$FINAL_MAIN_SHA" "$CANDIDATE_SHA"' in final_gate
    assert "origin/main advanced during CI" in final_gate
    assert "STALE_MAIN_FINAL_GATE=PASS" in final_gate
    assert final_gate.index("STALE_MAIN_FINAL_GATE=PASS") < final_gate.index(
        "CI_SELF_TEST=PASS"
    )


def test_commander_boundary_discovery_is_recursive_and_git_tracked():
    """Nested Commander regressions must be selected by the focused fail-closed gate."""
    text = _ci_text()
    start = "- name: Run production Commander boundary regression"
    end = "- name: Run full regression"

    assert start in text
    assert end in text
    commander_gate = text.split(start, 1)[1].split(end, 1)[0]

    assert "git ls-files -z --" in commander_gate
    assert "find tests -maxdepth 1" not in commander_gate
    assert "mapfile -d '' -t focused" in commander_gate
    required_patterns = (
        "test_systemd_commander_integration*.py",
        "test_systemd_production_commander*.py",
        "test_systemd_production_activation_runtime*.py",
        "test_systemd_production_runtime_delegation*.py",
        "test_systemd_production_execution_delegation*.py",
        "test_systemd_production_explicit_runtime*.py",
    )
    for pattern in required_patterns:
        assert f":(glob)tests/**/{pattern}" in commander_gate

    assert "COMMANDER_DISCOVERY_COUNT=" in commander_gate
    assert "COMMANDER_DISCOVERY=PASS" in commander_gate
    assert commander_gate.index("COMMANDER_DISCOVERY=PASS") < commander_gate.index(
        "python -m pytest -q -p no:cacheprovider"
    )


def test_ci_dependency_manifest_is_exact_and_bounded():
    """New CI dependencies require an explicit Lane 5 contract update, not silent drift."""
    dependencies = [
        line.strip()
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert dependencies == ["pytest>=8.4,<9", "PyYAML>=6.0,<7"]


def test_ci_dependency_resolution_and_pip_bootstrap_are_locked():
    """The same commit must not resolve a different Python test toolchain over time."""
    text = _ci_text()
    locked_dependencies = [
        line.strip()
        for line in REQUIREMENTS_LOCK.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert locked_dependencies == [
        "pytest==8.4.2",
        "PyYAML==6.0.3",
        "iniconfig==2.3.0",
        "packaging==26.3",
        "pluggy==1.6.0",
        "Pygments==2.21.0",
    ]
    assert "python -m pip install --upgrade pip" not in text
    assert 'CI_PIP_VERSION="26.2.1"' in text
    assert 'python -m pip install "pip==${CI_PIP_VERSION}"' in text
    assert "cache-dependency-path: requirements-dev-lock.txt" in text
    assert "python -m pip install -r requirements-dev-lock.txt" in text
    assert "- name: Verify dependency contract\n        timeout-minutes: 3" in text
    assert "resolved dependency drift" in text
    assert "PIP_BOOTSTRAP_CONTRACT=PASS" in text
    assert "DEV_DEPENDENCY_LOCK=PASS" in text


def test_all_workflow_actions_are_reviewed_sha_pins():
    """Every repository workflow must fail closed on mutable or unreviewed actions."""
    action_pattern = re.compile(
        r"^\s*uses:\s+([^@\s]+)@([0-9a-f]{40})(?:\s+#.*)?$",
        re.MULTILINE,
    )
    workflows = _workflow_files()
    discovered: dict[str, str] = {}
    action_reference_count = 0

    assert workflows, "no GitHub Actions workflow files discovered"
    assert CI_WORKFLOW in workflows, "canonical CI workflow missing"

    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        action_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("uses: ")
        ]
        matches = action_pattern.findall(text)

        assert len(matches) == len(action_lines), (
            f"mutable or malformed action reference in {workflow.name}"
        )

        for action, commit_sha in matches:
            assert action in PINNED_ACTIONS, (
                f"unreviewed action dependency in {workflow.name}: {action}"
            )
            assert commit_sha == PINNED_ACTIONS[action], (
                f"action pin drift in {workflow.name}: {action}@{commit_sha}"
            )
            discovered[action] = commit_sha
            action_reference_count += 1

    assert action_reference_count > 0, "no external action references discovered"

    public_distribution = WORKFLOW_DIR / "public-distribution.yml"
    if public_distribution.exists():
        assert discovered == PINNED_ACTIONS
