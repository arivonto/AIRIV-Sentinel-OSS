from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sentinel.release_artifact_validation import ReleaseArtifactProvenance
from sentinel.release_planning import (
    ReleaseArtifactManifest,
    RollbackCandidate,
    UpgradePlan,
)
from sentinel.upgrade_verification import (
    PostUpgradeObservation,
    PostUpgradeVerificationDecision,
    PostUpgradeVerificationStatus,
    PostUpgradeVerifier,
)


CURRENT = "1" * 40
TARGET = "2" * 40
TREE = "3" * 40
MANIFEST_DIGEST = "4" * 64
ARCHIVE = "5" * 64
COMPONENT = "6" * 64


def _manifest() -> ReleaseArtifactManifest:
    return ReleaseArtifactManifest(
        release_id="airiv-sentinel-upgrade-test",
        commit_sha=TARGET,
        tree_sha=TREE,
        created_at="2026-09-09T10:00:00+07:00",
        runtime_entrypoint="python -m sentinel",
        python_series="3.14",
        components={"sentinel/__main__.py": COMPONENT},
    )


def _plan(manifest: ReleaseArtifactManifest | None = None, **overrides) -> UpgradePlan:
    manifest = manifest or _manifest()
    values = {
        "from_sha": CURRENT,
        "to_sha": TARGET,
        "manifest_sha256": manifest.sha256,
        "requires_restart": True,
        "rollback_candidate": RollbackCandidate(
            candidate_sha=CURRENT,
            failed_target_sha=TARGET,
        ),
    }
    values.update(overrides)
    return UpgradePlan(**values)


def _provenance(manifest: ReleaseArtifactManifest | None = None, **overrides) -> ReleaseArtifactProvenance:
    manifest = manifest or _manifest()
    values = {
        "release_id": manifest.release_id,
        "commit_sha": manifest.commit_sha,
        "tree_sha": manifest.tree_sha,
        "manifest_sha256": manifest.sha256,
        "archive_sha256": ARCHIVE,
        "component_count": len(manifest.components),
    }
    values.update(overrides)
    return ReleaseArtifactProvenance(**values)


def _observation(manifest: ReleaseArtifactManifest | None = None, **overrides) -> PostUpgradeObservation:
    manifest = manifest or _manifest()
    values = {
        "deployed_head": manifest.commit_sha,
        "service_active": True,
        "runtime_entrypoint": manifest.runtime_entrypoint,
        "python_series": manifest.python_series,
        "manifest_sha256": manifest.sha256,
        "archive_sha256": ARCHIVE,
    }
    values.update(overrides)
    return PostUpgradeObservation(**values)


def test_exact_post_upgrade_state_is_verified_without_rollback_authority() -> None:
    manifest = _manifest()
    decision = PostUpgradeVerifier.verify(
        _plan(manifest),
        manifest,
        _provenance(manifest),
        _observation(manifest),
    )

    assert decision.status == PostUpgradeVerificationStatus.VERIFIED
    assert decision.reason_code == "POST_UPGRADE_VERIFIED"
    assert decision.expected_head == TARGET
    assert decision.observed_head == TARGET
    assert decision.rollback_authorized is False
    with pytest.raises(FrozenInstanceError):
        decision.rollback_authorized = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "deployed_head",
        "service_active",
        "runtime_entrypoint",
        "python_series",
        "manifest_sha256",
        "archive_sha256",
    ],
)
def test_incomplete_observation_is_unknown(field: str) -> None:
    manifest = _manifest()
    decision = PostUpgradeVerifier.verify(
        _plan(manifest),
        manifest,
        _provenance(manifest),
        _observation(manifest, **{field: None}),
    )

    assert decision.status == PostUpgradeVerificationStatus.UNKNOWN
    assert decision.reason_code == "OBSERVATION_INCOMPLETE"
    assert decision.rollback_authorized is False


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"deployed_head": "7" * 40}, "DEPLOYED_HEAD_MISMATCH"),
        ({"manifest_sha256": "8" * 64}, "MANIFEST_DIGEST_MISMATCH"),
        ({"archive_sha256": "9" * 64}, "ARCHIVE_DIGEST_MISMATCH"),
        ({"runtime_entrypoint": "python -m sentinel.other"}, "RUNTIME_ENTRYPOINT_MISMATCH"),
        ({"python_series": "3.13"}, "PYTHON_SERIES_MISMATCH"),
        ({"service_active": False}, "SERVICE_NOT_ACTIVE"),
    ],
)
def test_observed_mismatch_is_failed_without_auto_rollback(overrides, reason) -> None:
    manifest = _manifest()
    decision = PostUpgradeVerifier.verify(
        _plan(manifest),
        manifest,
        _provenance(manifest),
        _observation(manifest, **overrides),
    )

    assert decision.status == PostUpgradeVerificationStatus.FAILED
    assert decision.reason_code == reason
    assert decision.rollback_authorized is False


def test_composition_mismatch_is_rejected_before_observation_is_trusted() -> None:
    manifest = _manifest()

    with pytest.raises(ValueError, match="plan target"):
        PostUpgradeVerifier.verify(
            _plan(manifest, to_sha="a" * 40),
            manifest,
            _provenance(manifest),
            _observation(manifest),
        )
    with pytest.raises(ValueError, match="plan manifest"):
        PostUpgradeVerifier.verify(
            _plan(manifest, manifest_sha256="b" * 64),
            manifest,
            _provenance(manifest),
            _observation(manifest),
        )
    with pytest.raises(ValueError, match="provenance commit"):
        PostUpgradeVerifier.verify(
            _plan(manifest),
            manifest,
            _provenance(manifest, commit_sha="c" * 40),
            _observation(manifest),
        )
    with pytest.raises(ValueError, match="provenance tree"):
        PostUpgradeVerifier.verify(
            _plan(manifest),
            manifest,
            _provenance(manifest, tree_sha="d" * 40),
            _observation(manifest),
        )
    with pytest.raises(ValueError, match="provenance manifest"):
        PostUpgradeVerifier.verify(
            _plan(manifest),
            manifest,
            _provenance(manifest, manifest_sha256="e" * 64),
            _observation(manifest),
        )


def test_decision_cannot_claim_rollback_authority() -> None:
    with pytest.raises(ValueError, match="cannot authorize rollback"):
        PostUpgradeVerificationDecision(
            status=PostUpgradeVerificationStatus.FAILED,
            reason_code="SERVICE_NOT_ACTIVE",
            expected_head=TARGET,
            observed_head=TARGET,
            rollback_authorized=True,
        )


def test_observation_rejects_malformed_facts() -> None:
    with pytest.raises(ValueError, match="deployed_head"):
        _observation(deployed_head="not-a-sha")
    with pytest.raises(TypeError, match="service_active"):
        _observation(service_active=1)
    with pytest.raises(ValueError, match="runtime_entrypoint"):
        _observation(runtime_entrypoint="")
    with pytest.raises(ValueError, match="manifest_sha256"):
        _observation(manifest_sha256="bad")


def test_wrong_boundary_types_fail_closed() -> None:
    manifest = _manifest()
    plan = _plan(manifest)
    provenance = _provenance(manifest)
    observation = _observation(manifest)

    with pytest.raises(TypeError, match="plan must be"):
        PostUpgradeVerifier.verify(object(), manifest, provenance, observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="manifest must be"):
        PostUpgradeVerifier.verify(plan, object(), provenance, observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="provenance must be"):
        PostUpgradeVerifier.verify(plan, manifest, object(), observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation must be"):
        PostUpgradeVerifier.verify(plan, manifest, provenance, object())  # type: ignore[arg-type]


def test_module_has_no_execution_network_or_authority_imports() -> None:
    source = Path("sentinel/upgrade_verification.py").read_text(encoding="utf-8")
    forbidden = (
        "import os",
        "import subprocess",
        "import socket",
        "import requests",
        "import httpx",
        "import urllib",
        "systemctl",
        "git reset",
        "git checkout",
        "IncidentManager",
        "RemediationPolicy",
        "ExecutionBoundary",
    )
    for marker in forbidden:
        assert marker not in source
