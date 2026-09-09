"""Independent read-only post-upgrade verification for AIRIV Sentinel.

The verifier compares an already-created upgrade plan and verified release
provenance with observed post-upgrade state. It cannot deploy, restart,
rollback, authorize remediation, mutate Incident lifecycle, or execute shell
commands. Incomplete observation is terminally indeterminate for this check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sentinel.release_artifact_validation import ReleaseArtifactProvenance
from sentinel.release_planning import ReleaseArtifactManifest, UpgradePlan


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class PostUpgradeVerificationStatus:
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


def _require_sha(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase 40-character Git SHA-1 hex")
    return value


def _require_digest(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase SHA-256 hex")
    return value


def _require_optional_text(value: str | None, field: str, max_length: int = 256) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty when observed")
    normalized = value.strip()
    if len(normalized) > max_length or any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} is invalid")
    return normalized


@dataclass(frozen=True, slots=True)
class PostUpgradeObservation:
    """Observed state from an independent inspection boundary.

    ``None`` means the fact could not be established. It is not equivalent to
    a negative observation.
    """

    deployed_head: str | None
    service_active: bool | None
    runtime_entrypoint: str | None
    python_series: str | None
    manifest_sha256: str | None
    archive_sha256: str | None
    schema: str = "AIRIV_SENTINEL_POST_UPGRADE_OBSERVATION_V1"

    def __post_init__(self) -> None:
        if self.deployed_head is not None:
            object.__setattr__(
                self,
                "deployed_head",
                _require_sha(self.deployed_head, "deployed_head"),
            )
        if self.service_active is not None and not isinstance(self.service_active, bool):
            raise TypeError("service_active must be boolean or None")
        object.__setattr__(
            self,
            "runtime_entrypoint",
            _require_optional_text(self.runtime_entrypoint, "runtime_entrypoint"),
        )
        object.__setattr__(
            self,
            "python_series",
            _require_optional_text(self.python_series, "python_series", 32),
        )
        if self.manifest_sha256 is not None:
            object.__setattr__(
                self,
                "manifest_sha256",
                _require_digest(self.manifest_sha256, "manifest_sha256"),
            )
        if self.archive_sha256 is not None:
            object.__setattr__(
                self,
                "archive_sha256",
                _require_digest(self.archive_sha256, "archive_sha256"),
            )
        if self.schema != "AIRIV_SENTINEL_POST_UPGRADE_OBSERVATION_V1":
            raise ValueError("unsupported post-upgrade observation schema")

    @property
    def complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.deployed_head,
                self.service_active,
                self.runtime_entrypoint,
                self.python_series,
                self.manifest_sha256,
                self.archive_sha256,
            )
        )


@dataclass(frozen=True, slots=True)
class PostUpgradeVerificationDecision:
    status: str
    reason_code: str
    expected_head: str
    observed_head: str | None
    rollback_authorized: bool = False

    def __post_init__(self) -> None:
        if self.status not in {
            PostUpgradeVerificationStatus.VERIFIED,
            PostUpgradeVerificationStatus.FAILED,
            PostUpgradeVerificationStatus.UNKNOWN,
        }:
            raise ValueError("unsupported post-upgrade verification status")
        if not isinstance(self.reason_code, str) or not self.reason_code.strip():
            raise ValueError("reason_code is required")
        object.__setattr__(self, "reason_code", self.reason_code.strip())
        object.__setattr__(
            self,
            "expected_head",
            _require_sha(self.expected_head, "expected_head"),
        )
        if self.observed_head is not None:
            object.__setattr__(
                self,
                "observed_head",
                _require_sha(self.observed_head, "observed_head"),
            )
        if self.rollback_authorized is not False:
            raise ValueError("post-upgrade verification cannot authorize rollback")


class PostUpgradeVerifier:
    """Fail-closed independent comparison of expected and observed state."""

    @staticmethod
    def verify(
        plan: UpgradePlan,
        manifest: ReleaseArtifactManifest,
        provenance: ReleaseArtifactProvenance,
        observation: PostUpgradeObservation,
    ) -> PostUpgradeVerificationDecision:
        if not isinstance(plan, UpgradePlan):
            raise TypeError("plan must be an UpgradePlan")
        if not isinstance(manifest, ReleaseArtifactManifest):
            raise TypeError("manifest must be a ReleaseArtifactManifest")
        if not isinstance(provenance, ReleaseArtifactProvenance):
            raise TypeError("provenance must be ReleaseArtifactProvenance")
        if not isinstance(observation, PostUpgradeObservation):
            raise TypeError("observation must be PostUpgradeObservation")

        if plan.to_sha != manifest.commit_sha:
            raise ValueError("upgrade plan target does not match release manifest")
        if plan.manifest_sha256 != manifest.sha256:
            raise ValueError("upgrade plan manifest digest does not match release manifest")
        if provenance.commit_sha != manifest.commit_sha:
            raise ValueError("release provenance commit does not match release manifest")
        if provenance.tree_sha != manifest.tree_sha:
            raise ValueError("release provenance tree does not match release manifest")
        if provenance.manifest_sha256 != manifest.sha256:
            raise ValueError("release provenance manifest digest does not match release manifest")

        expected_head = plan.to_sha
        if observation.complete is not True:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.UNKNOWN,
                reason_code="OBSERVATION_INCOMPLETE",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.deployed_head != expected_head:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="DEPLOYED_HEAD_MISMATCH",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.manifest_sha256 != manifest.sha256:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="MANIFEST_DIGEST_MISMATCH",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.archive_sha256 != provenance.archive_sha256:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="ARCHIVE_DIGEST_MISMATCH",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.runtime_entrypoint != manifest.runtime_entrypoint:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="RUNTIME_ENTRYPOINT_MISMATCH",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.python_series != manifest.python_series:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="PYTHON_SERIES_MISMATCH",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )
        if observation.service_active is not True:
            return PostUpgradeVerificationDecision(
                status=PostUpgradeVerificationStatus.FAILED,
                reason_code="SERVICE_NOT_ACTIVE",
                expected_head=expected_head,
                observed_head=observation.deployed_head,
            )

        return PostUpgradeVerificationDecision(
            status=PostUpgradeVerificationStatus.VERIFIED,
            reason_code="POST_UPGRADE_VERIFIED",
            expected_head=expected_head,
            observed_head=observation.deployed_head,
        )
