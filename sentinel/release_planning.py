"""Read-only release, upgrade and rollback planning for AIRIV Sentinel.

This module deliberately owns no repository mutation, shell execution, service
restart, deployment, rollback authorization, remediation policy, or Incident
lifecycle authority. It converts already-observed release facts into immutable,
deterministic planning artifacts only.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Mapping


_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class UpgradePreflightStatus:
    READY = "READY"
    NOT_READY = "NOT_READY"


class RollbackAuthorizationState:
    UNAUTHORIZED = "UNAUTHORIZED"


def _require_sha(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX40.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase 40-character Git SHA-1 hex")
    return value


def _require_digest(value: str, field: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{field} must be lowercase SHA-256 hex")
    return value


def _require_text(value: str, field: str, *, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field} is too long")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field} contains control characters")
    return normalized


def _require_aware_timestamp(value: str) -> str:
    normalized = _require_text(value, "created_at")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("created_at must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("created_at must include timezone information")
    return parsed.astimezone(timezone.utc).isoformat()


def _normalize_component_path(path: str) -> str:
    normalized = _require_text(path, "component path", max_length=512)
    if normalized.startswith("/"):
        raise ValueError("component path must be repository-relative")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("component path must be normalized and repository-relative")
    return normalized


def _freeze_components(components: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(components, Mapping) or not components:
        raise ValueError("components must be a non-empty mapping")
    normalized: dict[str, str] = {}
    for raw_path, raw_digest in components.items():
        path = _normalize_component_path(raw_path)
        if path in normalized:
            raise ValueError("component paths must be unique")
        normalized[path] = _require_digest(raw_digest, f"component digest for {path}")
    return MappingProxyType(dict(sorted(normalized.items())))


@dataclass(frozen=True, slots=True)
class ReleaseArtifactManifest:
    """Immutable release identity and reviewed component digests."""

    release_id: str
    commit_sha: str
    tree_sha: str
    created_at: str
    runtime_entrypoint: str
    python_series: str
    components: Mapping[str, str]
    schema: str = "AIRIV_SENTINEL_RELEASE_ARTIFACT_MANIFEST_V1"

    def __post_init__(self) -> None:
        if not isinstance(self.release_id, str) or _RELEASE_ID.fullmatch(self.release_id) is None:
            raise ValueError("release_id contains unsupported characters or length")
        object.__setattr__(self, "commit_sha", _require_sha(self.commit_sha, "commit_sha"))
        object.__setattr__(self, "tree_sha", _require_sha(self.tree_sha, "tree_sha"))
        object.__setattr__(self, "created_at", _require_aware_timestamp(self.created_at))
        object.__setattr__(
            self,
            "runtime_entrypoint",
            _require_text(self.runtime_entrypoint, "runtime_entrypoint"),
        )
        object.__setattr__(
            self,
            "python_series",
            _require_text(self.python_series, "python_series", max_length=32),
        )
        object.__setattr__(self, "components", _freeze_components(self.components))
        if self.schema != "AIRIV_SENTINEL_RELEASE_ARTIFACT_MANIFEST_V1":
            raise ValueError("unsupported release manifest schema")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
            "tree_sha": self.tree_sha,
            "created_at": self.created_at,
            "runtime_entrypoint": self.runtime_entrypoint,
            "python_series": self.python_series,
            "components": dict(self.components),
        }

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class UpgradeRepositoryFacts:
    """Observed repository facts supplied by a separate inspection boundary."""

    current_head: str
    target_head: str
    origin_main: str
    clean_worktree: bool
    target_is_descendant: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_head", _require_sha(self.current_head, "current_head"))
        object.__setattr__(self, "target_head", _require_sha(self.target_head, "target_head"))
        object.__setattr__(self, "origin_main", _require_sha(self.origin_main, "origin_main"))
        if not isinstance(self.clean_worktree, bool):
            raise TypeError("clean_worktree must be boolean")
        if not isinstance(self.target_is_descendant, bool):
            raise TypeError("target_is_descendant must be boolean")


@dataclass(frozen=True, slots=True)
class RollbackCandidate:
    """Forensic rollback candidate only; never an authorization or command."""

    candidate_sha: str
    failed_target_sha: str
    authorization_state: str = RollbackAuthorizationState.UNAUTHORIZED
    executable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_sha", _require_sha(self.candidate_sha, "candidate_sha"))
        object.__setattr__(
            self,
            "failed_target_sha",
            _require_sha(self.failed_target_sha, "failed_target_sha"),
        )
        if self.authorization_state != RollbackAuthorizationState.UNAUTHORIZED:
            raise ValueError("rollback planning cannot authorize rollback")
        if self.executable is not False:
            raise ValueError("rollback planning cannot make rollback executable")


@dataclass(frozen=True, slots=True)
class UpgradePlan:
    from_sha: str
    to_sha: str
    manifest_sha256: str
    requires_restart: bool
    rollback_candidate: RollbackCandidate

    def __post_init__(self) -> None:
        object.__setattr__(self, "from_sha", _require_sha(self.from_sha, "from_sha"))
        object.__setattr__(self, "to_sha", _require_sha(self.to_sha, "to_sha"))
        object.__setattr__(
            self,
            "manifest_sha256",
            _require_digest(self.manifest_sha256, "manifest_sha256"),
        )
        if not isinstance(self.requires_restart, bool):
            raise TypeError("requires_restart must be boolean")
        if not isinstance(self.rollback_candidate, RollbackCandidate):
            raise TypeError("rollback_candidate must be a RollbackCandidate")


@dataclass(frozen=True, slots=True)
class UpgradePreflightDecision:
    status: str
    reason_code: str
    manifest_sha256: str
    plan: UpgradePlan | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            UpgradePreflightStatus.READY,
            UpgradePreflightStatus.NOT_READY,
        }:
            raise ValueError("unsupported upgrade preflight status")
        object.__setattr__(self, "reason_code", _require_text(self.reason_code, "reason_code"))
        object.__setattr__(
            self,
            "manifest_sha256",
            _require_digest(self.manifest_sha256, "manifest_sha256"),
        )
        if self.status == UpgradePreflightStatus.READY and self.plan is None:
            raise ValueError("READY preflight requires a plan")
        if self.status == UpgradePreflightStatus.NOT_READY and self.plan is not None:
            raise ValueError("NOT_READY preflight cannot contain an executable plan")


class UpgradePreflight:
    """Pure planning boundary over previously observed immutable facts."""

    @staticmethod
    def evaluate(
        manifest: ReleaseArtifactManifest,
        facts: UpgradeRepositoryFacts,
    ) -> UpgradePreflightDecision:
        if not isinstance(manifest, ReleaseArtifactManifest):
            raise TypeError("manifest must be a ReleaseArtifactManifest")
        if not isinstance(facts, UpgradeRepositoryFacts):
            raise TypeError("facts must be UpgradeRepositoryFacts")

        digest = manifest.sha256
        if facts.clean_worktree is not True:
            return UpgradePreflightDecision(
                status=UpgradePreflightStatus.NOT_READY,
                reason_code="WORKTREE_NOT_CLEAN",
                manifest_sha256=digest,
            )
        if facts.target_head != manifest.commit_sha:
            return UpgradePreflightDecision(
                status=UpgradePreflightStatus.NOT_READY,
                reason_code="TARGET_MANIFEST_COMMIT_MISMATCH",
                manifest_sha256=digest,
            )
        if facts.origin_main != facts.target_head:
            return UpgradePreflightDecision(
                status=UpgradePreflightStatus.NOT_READY,
                reason_code="TARGET_NOT_ORIGIN_MAIN",
                manifest_sha256=digest,
            )
        if facts.current_head != facts.target_head and facts.target_is_descendant is not True:
            return UpgradePreflightDecision(
                status=UpgradePreflightStatus.NOT_READY,
                reason_code="TARGET_NOT_FAST_FORWARD_DESCENDANT",
                manifest_sha256=digest,
            )

        requires_restart = facts.current_head != facts.target_head
        return UpgradePreflightDecision(
            status=UpgradePreflightStatus.READY,
            reason_code=("UPGRADE_READY" if requires_restart else "ALREADY_CURRENT"),
            manifest_sha256=digest,
            plan=UpgradePlan(
                from_sha=facts.current_head,
                to_sha=facts.target_head,
                manifest_sha256=digest,
                requires_restart=requires_restart,
                rollback_candidate=RollbackCandidate(
                    candidate_sha=facts.current_head,
                    failed_target_sha=facts.target_head,
                ),
            ),
        )
