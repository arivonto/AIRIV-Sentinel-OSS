from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from sentinel.release_artifact_validation import (
    ReleaseArtifactObservation,
    ReleaseArtifactProvenance,
    ReleaseArtifactValidationDecision,
    ReleaseArtifactValidationStatus,
    ReleaseArtifactValidator,
)
from sentinel.release_planning import ReleaseArtifactManifest


COMMIT = "a" * 40
TREE = "b" * 40
ARCHIVE = "c" * 64
FILE_A = "d" * 64
FILE_B = "e" * 64


def _manifest() -> ReleaseArtifactManifest:
    return ReleaseArtifactManifest(
        release_id="sentinel-v1-test",
        commit_sha=COMMIT,
        tree_sha=TREE,
        created_at="2026-09-09T10:00:00+07:00",
        runtime_entrypoint="python -m sentinel",
        python_series="3.14",
        components={
            "sentinel/__main__.py": FILE_A,
            "sentinel/runtime.py": FILE_B,
        },
    )


def _observation(
    *,
    manifest: ReleaseArtifactManifest | None = None,
    commit_sha: str = COMMIT,
    tree_sha: str = TREE,
    manifest_sha256: str | None = None,
    archive_sha256: str = ARCHIVE,
    components: dict[str, str] | None = None,
) -> ReleaseArtifactObservation:
    manifest = manifest or _manifest()
    return ReleaseArtifactObservation(
        commit_sha=commit_sha,
        tree_sha=tree_sha,
        manifest_sha256=manifest_sha256 or manifest.sha256,
        archive_sha256=archive_sha256,
        components=components
        or {
            "sentinel/__main__.py": FILE_A,
            "sentinel/runtime.py": FILE_B,
        },
    )


def test_matching_observation_is_verified_with_immutable_provenance() -> None:
    manifest = _manifest()
    decision = ReleaseArtifactValidator.validate(manifest, _observation(manifest=manifest))

    assert decision.status == ReleaseArtifactValidationStatus.VERIFIED
    assert decision.reason_code == "ARTIFACT_VERIFIED"
    assert decision.provenance == ReleaseArtifactProvenance(
        release_id=manifest.release_id,
        commit_sha=COMMIT,
        tree_sha=TREE,
        manifest_sha256=manifest.sha256,
        archive_sha256=ARCHIVE,
        component_count=2,
    )
    assert decision.provenance.to_dict()["archive_sha256"] == ARCHIVE
    with pytest.raises(FrozenInstanceError):
        decision.provenance.component_count = 3  # type: ignore[misc]


def test_observation_components_are_defensively_frozen() -> None:
    source = {
        "sentinel/runtime.py": FILE_B,
        "sentinel/__main__.py": FILE_A,
    }
    observation = _observation(components=source)
    source["sentinel/runtime.py"] = "f" * 64

    assert observation.components["sentinel/runtime.py"] == FILE_B
    assert tuple(observation.components) == (
        "sentinel/__main__.py",
        "sentinel/runtime.py",
    )
    with pytest.raises(TypeError):
        observation.components["sentinel/runtime.py"] = "f" * 64  # type: ignore[index]


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"manifest_sha256": "f" * 64}, "MANIFEST_DIGEST_MISMATCH"),
        ({"commit_sha": "1" * 40}, "COMMIT_SHA_MISMATCH"),
        ({"tree_sha": "2" * 40}, "TREE_SHA_MISMATCH"),
        (
            {"components": {"sentinel/__main__.py": FILE_A}},
            "COMPONENT_SET_MISMATCH",
        ),
        (
            {
                "components": {
                    "sentinel/__main__.py": FILE_A,
                    "sentinel/runtime.py": FILE_B,
                    "sentinel/extra.py": "3" * 64,
                }
            },
            "COMPONENT_SET_MISMATCH",
        ),
        (
            {
                "components": {
                    "sentinel/__main__.py": FILE_A,
                    "sentinel/runtime.py": "4" * 64,
                }
            },
            "COMPONENT_DIGEST_MISMATCH",
        ),
    ],
)
def test_validation_rejects_identity_or_component_tampering(
    kwargs: dict[str, object],
    reason: str,
) -> None:
    manifest = _manifest()
    decision = ReleaseArtifactValidator.validate(manifest, _observation(manifest=manifest, **kwargs))

    assert decision.status == ReleaseArtifactValidationStatus.REJECTED
    assert decision.reason_code == reason
    assert decision.provenance is None


def test_fail_closed_reason_precedence_starts_with_manifest_binding() -> None:
    manifest = _manifest()
    decision = ReleaseArtifactValidator.validate(
        manifest,
        _observation(
            manifest=manifest,
            manifest_sha256="f" * 64,
            commit_sha="1" * 40,
            tree_sha="2" * 40,
            components={"sentinel/__main__.py": "3" * 64},
        ),
    )

    assert decision.reason_code == "MANIFEST_DIGEST_MISMATCH"


def test_rejected_decision_cannot_smuggle_provenance() -> None:
    provenance = ReleaseArtifactProvenance(
        release_id="sentinel-v1-test",
        commit_sha=COMMIT,
        tree_sha=TREE,
        manifest_sha256="5" * 64,
        archive_sha256=ARCHIVE,
        component_count=1,
    )
    with pytest.raises(ValueError, match="REJECTED validation cannot contain provenance"):
        ReleaseArtifactValidationDecision(
            status=ReleaseArtifactValidationStatus.REJECTED,
            reason_code="REJECTED",
            provenance=provenance,
        )


def test_verified_decision_requires_provenance() -> None:
    with pytest.raises(ValueError, match="VERIFIED validation requires provenance"):
        ReleaseArtifactValidationDecision(
            status=ReleaseArtifactValidationStatus.VERIFIED,
            reason_code="ARTIFACT_VERIFIED",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"commit_sha": "A" * 40},
        {"tree_sha": "bad"},
        {"manifest_sha256": "g" * 64},
        {"archive_sha256": "short"},
        {"components": {"../escape": FILE_A}},
        {"components": {"/absolute": FILE_A}},
    ],
)
def test_observation_rejects_malformed_or_unsafe_facts(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        _observation(**kwargs)


def test_validator_rejects_wrong_boundary_types() -> None:
    manifest = _manifest()
    observation = _observation(manifest=manifest)

    with pytest.raises(TypeError, match="manifest must be"):
        ReleaseArtifactValidator.validate(object(), observation)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="observation must be"):
        ReleaseArtifactValidator.validate(manifest, object())  # type: ignore[arg-type]


def test_module_has_no_execution_network_or_authority_imports() -> None:
    source = Path("sentinel/release_artifact_validation.py").read_text(encoding="utf-8")
    forbidden = (
        "import os",
        "import subprocess",
        "import socket",
        "import requests",
        "import httpx",
        "import urllib",
        "systemctl",
        "IncidentManager",
        "RemediationPolicy",
        "ExecutionBoundary",
    )

    for marker in forbidden:
        assert marker not in source
