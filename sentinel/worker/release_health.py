"""Detached release and upgrade health projections with no runtime authority."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class ProjectionHealth(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReleaseReadinessHealthProjection:
    total_records: int
    ready_count: int
    not_ready_count: int
    unknown_record_count: int
    duplicate_release_id_count: int
    health: ProjectionHealth


@dataclass(frozen=True)
class ArtifactValidationHealthProjection:
    total_records: int
    verified_count: int
    rejected_count: int
    unknown_record_count: int
    duplicate_artifact_id_count: int
    health: ProjectionHealth


@dataclass(frozen=True)
class PostUpgradeVerificationHealthProjection:
    total_records: int
    verified_count: int
    failed_count: int
    unknown_record_count: int
    duplicate_verification_id_count: int
    rollback_authority_violation_count: int
    health: ProjectionHealth


def _stable_id(record: Mapping[str, Any], field: str) -> str | None:
    value = record.get(field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _health(*, total: int, degraded: bool) -> ProjectionHealth:
    if total == 0:
        return ProjectionHealth.UNKNOWN
    return ProjectionHealth.DEGRADED if degraded else ProjectionHealth.HEALTHY


def project_release_readiness(
    records: Iterable[Mapping[str, Any]],
) -> ReleaseReadinessHealthProjection:
    """Project detached UpgradePreflight-style readiness facts only."""
    total = ready = not_ready = unknown = duplicates = 0
    identities: set[str] = set()

    for record in records:
        total += 1
        record_unknown = False
        release_id = _stable_id(record, "release_id")
        if release_id is None:
            record_unknown = True
        elif release_id in identities:
            duplicates += 1
        else:
            identities.add(release_id)

        status = record.get("status")
        if status == "READY":
            ready += 1
        elif status == "NOT_READY":
            not_ready += 1
        else:
            record_unknown = True

        unknown += int(record_unknown)

    return ReleaseReadinessHealthProjection(
        total_records=total,
        ready_count=ready,
        not_ready_count=not_ready,
        unknown_record_count=unknown,
        duplicate_release_id_count=duplicates,
        health=_health(
            total=total,
            degraded=bool(not_ready or unknown or duplicates),
        ),
    )


def project_artifact_validation_health(
    records: Iterable[Mapping[str, Any]],
) -> ArtifactValidationHealthProjection:
    """Project detached release-artifact validation facts only."""
    total = verified = rejected = unknown = duplicates = 0
    identities: set[str] = set()

    for record in records:
        total += 1
        record_unknown = False
        artifact_id = _stable_id(record, "artifact_id")
        if artifact_id is None:
            record_unknown = True
        elif artifact_id in identities:
            duplicates += 1
        else:
            identities.add(artifact_id)

        status = record.get("status")
        if status == "VERIFIED":
            verified += 1
        elif status == "REJECTED":
            rejected += 1
        else:
            record_unknown = True

        unknown += int(record_unknown)

    return ArtifactValidationHealthProjection(
        total_records=total,
        verified_count=verified,
        rejected_count=rejected,
        unknown_record_count=unknown,
        duplicate_artifact_id_count=duplicates,
        health=_health(
            total=total,
            degraded=bool(rejected or unknown or duplicates),
        ),
    )


def project_post_upgrade_verification_health(
    records: Iterable[Mapping[str, Any]],
) -> PostUpgradeVerificationHealthProjection:
    """Project detached post-upgrade verification facts without rollback authority."""
    total = verified = failed = unknown = duplicates = authority_violations = 0
    identities: set[str] = set()

    for record in records:
        total += 1
        record_unknown = False
        verification_id = _stable_id(record, "verification_id")
        if verification_id is None:
            record_unknown = True
        elif verification_id in identities:
            duplicates += 1
        else:
            identities.add(verification_id)

        status = record.get("status")
        if status == "VERIFIED":
            verified += 1
        elif status == "FAILED":
            failed += 1
        elif status == "UNKNOWN":
            record_unknown = True
        else:
            record_unknown = True

        rollback_authorized = record.get("rollback_authorized")
        if rollback_authorized is True:
            authority_violations += 1
        elif rollback_authorized is not False:
            record_unknown = True

        unknown += int(record_unknown)

    return PostUpgradeVerificationHealthProjection(
        total_records=total,
        verified_count=verified,
        failed_count=failed,
        unknown_record_count=unknown,
        duplicate_verification_id_count=duplicates,
        rollback_authority_violation_count=authority_violations,
        health=_health(
            total=total,
            degraded=bool(failed or unknown or duplicates or authority_violations),
        ),
    )
