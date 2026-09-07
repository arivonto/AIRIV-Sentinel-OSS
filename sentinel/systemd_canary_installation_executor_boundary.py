"""Preparation-only safety boundary for future canary installation.

This module has no host execution primitive.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from sentinel.systemd_canary_installation_plan import (
    COMMANDER_INSTALL_APPROVAL,
    CanaryInstallationPlan,
    CanaryPreMutationGateResult,
    evaluate_canary_pre_mutation_gate,
)
from sentinel.systemd_live_canary_preflight import (
    SystemdCanaryPreflight,
)


@dataclass(frozen=True, slots=True)
class CanaryInstallationExecutionEnvelope:
    plan_fingerprint: str
    design_fingerprint: str
    file_manifest_fingerprint: str

    unit_name: str
    component_id: str

    destination: str
    content_sha256: str
    owner_uid: int
    owner_gid: int
    mode: int

    install_argv: tuple[
        tuple[str, ...],
        ...,
    ]

    rollback_argv: tuple[
        tuple[str, ...],
        ...,
    ]

    privilege_result: str
    commander_approved: bool

    def __post_init__(self) -> None:
        if self.privilege_result != "AUTHORIZED":
            raise PermissionError(
                "execution envelope requires AUTHORIZED privilege"
            )

        if not self.commander_approved:
            raise PermissionError(
                "execution envelope requires Commander approval"
            )

        if (
            self.unit_name
            != "airiv-sentinel-remediation-canary.service"
        ):
            raise ValueError(
                "non-canonical canary unit"
            )

        if (
            self.component_id
            != "systemd:"
            + self.unit_name
        ):
            raise ValueError(
                "non-canonical canary component"
            )

        forbidden_unit = (
            "airiv-sentinel.service"
        )

        for argv in (
            self.install_argv
            + self.rollback_argv
        ):
            if forbidden_unit in argv:
                raise ValueError(
                    "production Sentinel mutation forbidden"
                )

    def canonical_dict(self) -> dict:
        return {
            "plan_fingerprint":
                self.plan_fingerprint,

            "design_fingerprint":
                self.design_fingerprint,

            "file_manifest_fingerprint":
                self.file_manifest_fingerprint,

            "unit_name":
                self.unit_name,

            "component_id":
                self.component_id,

            "destination":
                self.destination,

            "content_sha256":
                self.content_sha256,

            "owner_uid":
                self.owner_uid,

            "owner_gid":
                self.owner_gid,

            "mode":
                self.mode,

            "install_argv": [
                list(argv)
                for argv
                in self.install_argv
            ],

            "rollback_argv": [
                list(argv)
                for argv
                in self.rollback_argv
            ],

            "privilege_result":
                self.privilege_result,

            "commander_approved":
                self.commander_approved,
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(
            encoded
        ).hexdigest()


class CanaryInstallationExecutorSafetyBoundary:
    """Prepare exact future mutation data; never performs mutation."""

    def prepare(
        self,
        *,
        preflight: SystemdCanaryPreflight,
        plan: CanaryInstallationPlan,
        commander_approval: str | None,
    ) -> CanaryInstallationExecutionEnvelope:
        if not isinstance(
            preflight,
            SystemdCanaryPreflight,
        ):
            raise TypeError(
                "preflight must be SystemdCanaryPreflight"
            )

        if not isinstance(
            plan,
            CanaryInstallationPlan,
        ):
            raise TypeError(
                "plan must be CanaryInstallationPlan"
            )

        gate: CanaryPreMutationGateResult = (
            evaluate_canary_pre_mutation_gate(
                preflight=preflight,
                plan=plan,
                commander_approval=commander_approval,
            )
        )

        if not gate.ready:
            raise PermissionError(
                gate.reason
            )

        if (
            commander_approval
            != COMMANDER_INSTALL_APPROVAL
        ):
            raise PermissionError(
                "commander_approval_required"
            )

        if (
            gate.plan_fingerprint
            != plan.fingerprint
        ):
            raise PermissionError(
                "plan_fingerprint_mismatch"
            )

        if (
            gate.design_fingerprint
            != preflight.design.fingerprint
        ):
            raise PermissionError(
                "design_fingerprint_mismatch"
            )

        manifest = (
            plan.file_manifest
        )

        if (
            manifest.content_sha256
            != preflight.design.unit_sha256
        ):
            raise PermissionError(
                "unit_sha256_mismatch"
            )

        return CanaryInstallationExecutionEnvelope(
            plan_fingerprint=(
                plan.fingerprint
            ),

            design_fingerprint=(
                plan.design_fingerprint
            ),

            file_manifest_fingerprint=(
                manifest.fingerprint
            ),

            unit_name=(
                plan.unit_name
            ),

            component_id=(
                plan.component_id
            ),

            destination=(
                manifest.destination
            ),

            content_sha256=(
                manifest.content_sha256
            ),

            owner_uid=(
                manifest.owner_uid
            ),

            owner_gid=(
                manifest.owner_gid
            ),

            mode=(
                manifest.mode
            ),

            install_argv=tuple(
                command.argv
                for command
                in plan.install_commands
            ),

            rollback_argv=tuple(
                command.argv
                for command
                in plan.rollback_commands
            ),

            privilege_result=(
                preflight.privilege_result
            ),

            commander_approved=True,
        )
