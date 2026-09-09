"""Deterministic read-only release artifact validation for AIRIV Sentinel.

This boundary validates already-observed artifact facts against the canonical
``ReleaseArtifactManifest``. It performs no repository mutation, deployment,
service restart, rollback, network access, shell execution, or authorization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sentinel.release_planning import ReleaseArtifactManifest


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class ReleaseArtifactValidationStatus:
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


def _require_sha(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase 40-character Git SHA-1 hex")
    return value


def _require_digest(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase SHA-256 hex")
    return value


def _normalize_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("component path is required")
    path = value.strip()
    if len(path) > 512 or path.startswith("/"):
        raise ValueError("component path must be repository-relative")
    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("component path must be normalized and repository-relative")
    if any(ord(char) < 32 for char in path):
        raise ValueError("component path contains control characters")
    return path


def _freeze_components(components: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(components, Mapping) or not components:
        raise ValueError("components must be a non-empty mapping")
    normalized: dict[str, str] = {}
    for raw_path, raw_digest in components.items():
        path = _normalize_path(raw_path)
        if path in normalized:
            raise ValueError("component paths must be unique")
        normalized[path] = _require_digest(raw_digest, f"component digest for {path}")
    return MappingProxyType(dict(sorted(normalized.items())))


def _require_reason_code(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("reason_code is required")
    reason = value.strip()
    if len(reason) > 128 or any(ord(char) < 32 for char in reason):
        raise ValueError("reason_code is invalid")
    return reason


@dataclass(frozen=True, slots=True)
class ReleaseArtifactObservation:
    """Immutable facts produced by a separate artifact-inspection boundary."""

    commit_sha: str
    tree_sha: str
    manifest_sha256: str
    archive_sha256: str
    components: Mapping[str, str]
    schema: str = "AIRIV_SENTINEL_RELEASE_ARTIFACT_OBSERVATION_V1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "commit_sha", _require_sha(self.commit_sha, "commit_sha"))
        object.__setattr__(self, "tree_sha", _require_sha(self.tree_sha, "tree_sha"))
        object.__setattr__(
            self,
            "manifest_sha256",
            _require_digest(self.manifest_sha256, "manifest_sha256"),
        )
        object.__setattr__(
            self,
            "archive_sha256",
            _require_digest(self.archive_sha256, "archive_sha256"),
        )
        object.__setattr__(self, "components", _freeze_components(self.components))
        if self.schema != "AIRIV_SENTINEL_RELEASE_ARTIFACT_OBSERVATION_V1":
            raise ValueError("unsupported release artifact observation schema")


@dataclass(frozen=True, slots=True)
class ReleaseArtifactProvenance:
    """Verified immutable release identity; never deployment authorization."""

    release_id: str
    commit_sha: str
    tree_sha: str
    manifest_sha256: str
    archive_sha256: str
    component_count: int
    schema: str = "AIRIV_SENTINEL_RELEASE_ARTIFACT_PROVENANCE_V1"

    def __post_init__(self) -> None:
        if not isinstance(self.release_id, str) or not self.release_id.strip():
            raise ValueError("release_id is required")
        object.__setattr__(self, "release_id", self.release_id.strip())
        object.__setattr__(self, "commit_sha", _require_sha(self.commit_sha, "commit_sha"))
        object.__setattr__(self, "tree_sha", _require_sha(self.tree_sha, "tree_sha"))
        object.__setattr__(
            self,
            "manifest_sha256",
            _require_digest(self.manifest_sha256, "manifest_sha256"),
        )
        object.__setattr__(
            self,
            "archive_sha256",
            _require_digest(self.archive_sha256, "archive_sha256"),
        )
        if not isinstance(self.component_count, int) or isinstance(self.component_count, bool):
            raise TypeError("component_count must be an integer")
        if self.component_count <= 0:
            raise ValueError("component_count must be positive")
        if self.schema != "AIRIV_SENTINEL_RELEASE_ARTIFACT_PROVENANCE_V1":
            raise ValueError("unsupported release artifact provenance schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
            "tree_sha": self.tree_sha,
            "manifest_sha256": self.manifest_sha256,
            "archive_sha256": self.archive_sha256,
            "component_count": self.component_count,
        }


@dataclass(frozen=True, slots=True)
class ReleaseArtifactValidationDecision:
    status: str
    reason_code: str
    provenance: ReleaseArtifactProvenance | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            ReleaseArtifactValidationStatus.VERIFIED,
            ReleaseArtifactValidationStatus.REJECTED,
        }:
            raise ValueError("unsupported release artifact validation status")
        object.__setattr__(self, "reason_code", _require_reason_code(self.reason_code))
        if self.status == ReleaseArtifactValidationStatus.VERIFIED:
            if not isinstance(self.provenance, ReleaseArtifactProvenance):
                raise ValueError("VERIFIED validation requires provenance")
        elif self.provenance is not None:
            raise ValueError("REJECTED validation cannot contain provenance")


class ReleaseArtifactValidator:
    """Fail-closed exact comparison of a manifest and observed artifact facts."""

    @staticmethod
    def validate(
        manifest: ReleaseArtifactManifest,
        observation: ReleaseArtifactObservation,
    ) -> ReleaseArtifactValidationDecision:
        if not isinstance(manifest, ReleaseArtifactManifest):
            raise TypeError("manifest must be a ReleaseArtifactManifest")
        if not isinstance(observation, ReleaseArtifactObservation):
            raise TypeError("observation must be a ReleaseArtifactObservation")

        if observation.manifest_sha256 != manifest.sha256:
            return ReleaseArtifactValidationDecision(
                status=ReleaseArtifactValidationStatus.REJECTED,
                reason_code="MANIFEST_DIGEST_MISMATCH",
            )
        if observation.commit_sha != manifest.commit_sha:
            return ReleaseArtifactValidationDecision(
                status=ReleaseArtifactValidationStatus.REJECTED,
                reason_code="COMMIT_SHA_MISMATCH",
            )
        if observation.tree_sha != manifest.tree_sha:
            return ReleaseArtifactValidationDecision(
                status=ReleaseArtifactValidationStatus.REJECTED,
                reason_code="TREE_SHA_MISMATCH",
            )

        expected_paths = frozenset(manifest.components)
        observed_paths = frozenset(observation.components)
        if observed_paths != expected_paths:
            return ReleaseArtifactValidationDecision(
                status=ReleaseArtifactValidationStatus.REJECTED,
                reason_code="COMPONENT_SET_MISMATCH",
            )

        for path in sorted(expected_paths):
            if observation.components[path] != manifest.components[path]:
                return ReleaseArtifactValidationDecision(
                    status=ReleaseArtifactValidationStatus.REJECTED,
                    reason_code="COMPONENT_DIGEST_MISMATCH",
                )

        provenance = ReleaseArtifactProvenance(
            release_id=manifest.release_id,
            commit_sha=manifest.commit_sha,
            tree_sha=manifest.tree_sha,
            manifest_sha256=manifest.sha256,
            archive_sha256=observation.archive_sha256,
            component_count=len(manifest.components),
        )
        return ReleaseArtifactValidationDecision(
            status=ReleaseArtifactValidationStatus.VERIFIED,
            reason_code="ARTIFACT_VERIFIED",
            provenance=provenance,
        )
