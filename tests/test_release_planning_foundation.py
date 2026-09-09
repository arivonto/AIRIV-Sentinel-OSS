from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sentinel.release_planning import (
    ReleaseArtifactManifest,
    RollbackAuthorizationState,
    UpgradePreflight,
    UpgradePreflightStatus,
    UpgradeRepositoryFacts,
)


CURRENT = "1" * 40
TARGET = "2" * 40
TREE = "3" * 40
COMPONENT_SHA = "4" * 64


def make_manifest(**overrides):
    values = {
        "release_id": "airiv-sentinel-test-release",
        "commit_sha": TARGET,
        "tree_sha": TREE,
        "created_at": "2026-09-09T10:00:00+07:00",
        "runtime_entrypoint": "python -m sentinel",
        "python_series": "3.14",
        "components": {
            "sentinel/__main__.py": COMPONENT_SHA,
            "deployment/systemd/airiv-sentinel.service.in": "5" * 64,
        },
    }
    values.update(overrides)
    return ReleaseArtifactManifest(**values)


def make_facts(**overrides):
    values = {
        "current_head": CURRENT,
        "target_head": TARGET,
        "origin_main": TARGET,
        "clean_worktree": True,
        "target_is_descendant": True,
    }
    values.update(overrides)
    return UpgradeRepositoryFacts(**values)


def test_release_manifest_is_immutable_normalized_and_deterministic():
    components = {
        "sentinel/__main__.py": COMPONENT_SHA,
        "deployment/systemd/airiv-sentinel.service.in": "5" * 64,
    }
    manifest = make_manifest(components=components)
    components["sentinel/__main__.py"] = "6" * 64

    assert manifest.created_at == "2026-09-09T03:00:00+00:00"
    assert manifest.components["sentinel/__main__.py"] == COMPONENT_SHA
    assert len(manifest.sha256) == 64
    assert manifest.sha256 == make_manifest().sha256

    with pytest.raises(TypeError):
        manifest.components["new"] = "7" * 64
    with pytest.raises(FrozenInstanceError):
        manifest.commit_sha = CURRENT


def test_release_manifest_fingerprint_is_mapping_order_independent():
    first = make_manifest(
        components={
            "sentinel/__main__.py": COMPONENT_SHA,
            "deployment/systemd/airiv-sentinel.service.in": "5" * 64,
        }
    )
    second = make_manifest(
        components={
            "deployment/systemd/airiv-sentinel.service.in": "5" * 64,
            "sentinel/__main__.py": COMPONENT_SHA,
        }
    )

    assert first.to_dict() == second.to_dict()
    assert first.sha256 == second.sha256


def test_release_manifest_rejects_invalid_identity_path_digest_and_timestamp():
    with pytest.raises(ValueError, match="release_id"):
        make_manifest(release_id="bad release id")
    with pytest.raises(ValueError, match="commit_sha"):
        make_manifest(commit_sha="ABC")
    with pytest.raises(ValueError, match="repository-relative"):
        make_manifest(components={"/etc/passwd": COMPONENT_SHA})
    with pytest.raises(ValueError, match="normalized"):
        make_manifest(components={"sentinel/../secret": COMPONENT_SHA})
    with pytest.raises(ValueError, match="SHA-256"):
        make_manifest(components={"sentinel/__main__.py": "bad"})
    with pytest.raises(ValueError, match="timezone"):
        make_manifest(created_at="2026-09-09T10:00:00")


def test_upgrade_preflight_builds_read_only_fast_forward_plan():
    manifest = make_manifest()
    decision = UpgradePreflight.evaluate(manifest, make_facts())

    assert decision.status == UpgradePreflightStatus.READY
    assert decision.reason_code == "UPGRADE_READY"
    assert decision.manifest_sha256 == manifest.sha256
    assert decision.plan.from_sha == CURRENT
    assert decision.plan.to_sha == TARGET
    assert decision.plan.requires_restart is True
    assert decision.plan.rollback_candidate.candidate_sha == CURRENT
    assert decision.plan.rollback_candidate.failed_target_sha == TARGET
    assert (
        decision.plan.rollback_candidate.authorization_state
        == RollbackAuthorizationState.UNAUTHORIZED
    )
    assert decision.plan.rollback_candidate.executable is False
    assert not hasattr(decision.plan, "command")
    assert not hasattr(decision.plan, "execute")


def test_already_current_is_ready_noop_without_restart_requirement():
    manifest = make_manifest()
    decision = UpgradePreflight.evaluate(
        manifest,
        make_facts(
            current_head=TARGET,
            target_is_descendant=False,
        ),
    )

    assert decision.status == UpgradePreflightStatus.READY
    assert decision.reason_code == "ALREADY_CURRENT"
    assert decision.plan.requires_restart is False
    assert decision.plan.from_sha == decision.plan.to_sha == TARGET


@pytest.mark.parametrize(
    ("facts", "reason"),
    [
        (make_facts(clean_worktree=False), "WORKTREE_NOT_CLEAN"),
        (
            make_facts(target_head="6" * 40, origin_main="6" * 40),
            "TARGET_MANIFEST_COMMIT_MISMATCH",
        ),
        (make_facts(origin_main="7" * 40), "TARGET_NOT_ORIGIN_MAIN"),
        (
            make_facts(target_is_descendant=False),
            "TARGET_NOT_FAST_FORWARD_DESCENDANT",
        ),
    ],
)
def test_upgrade_preflight_fails_closed_on_unsafe_repository_facts(facts, reason):
    decision = UpgradePreflight.evaluate(make_manifest(), facts)

    assert decision.status == UpgradePreflightStatus.NOT_READY
    assert decision.reason_code == reason
    assert decision.plan is None


def test_repository_fact_types_and_shas_fail_closed():
    with pytest.raises(ValueError, match="current_head"):
        make_facts(current_head="not-a-sha")
    with pytest.raises(TypeError, match="clean_worktree"):
        make_facts(clean_worktree=1)
    with pytest.raises(TypeError, match="target_is_descendant"):
        make_facts(target_is_descendant=None)


def test_planning_module_has_no_execution_or_policy_import_surface():
    source = (
        Path(__file__).resolve().parents[1] / "sentinel" / "release_planning.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "import subprocess",
        "from subprocess",
        "import os",
        "os.system",
        "systemctl",
        "RemediationPolicy",
        "ExecutionBoundary",
        "IncidentManager",
        "git reset",
        "git rebase",
        "git checkout",
    )
    for marker in forbidden:
        assert marker not in source


def test_rollback_candidate_cannot_be_promoted_to_authorized_or_executable():
    candidate = UpgradePreflight.evaluate(make_manifest(), make_facts()).plan.rollback_candidate

    with pytest.raises(FrozenInstanceError):
        candidate.executable = True
    with pytest.raises(FrozenInstanceError):
        candidate.authorization_state = "AUTHORIZED"
