"""Read-only systemd canary installation safety plan.

Phase 2.13D.D7B.

This module builds immutable mutation planning data and evaluates the
pre-mutation Commander gate. It performs no host mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from sentinel.systemd_live_canary_preflight import (
    CANARY_FRAGMENT_PATH,
    CANARY_UNIT,
    CANARY_UNIT_TEXT,
    SENTINEL_UNIT,
    SystemdCanaryPreflight,
)


COMMANDER_INSTALL_APPROVAL = (
    "APPROVE CANARY INSTALL 2.13D.D7C"
)

SYSTEMCTL = "/usr/bin/systemctl"


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CanaryFileManifest:
    destination: str
    content: str
    content_sha256: str
    owner_uid: int
    owner_gid: int
    mode: int

    def __post_init__(self) -> None:
        if self.destination != CANARY_FRAGMENT_PATH:
            raise ValueError(
                "canary destination mismatch"
            )

        if self.content != CANARY_UNIT_TEXT:
            raise ValueError(
                "canary content mismatch"
            )

        expected_hash = sha256(
            self.content.encode("utf-8")
        ).hexdigest()

        if self.content_sha256 != expected_hash:
            raise ValueError(
                "canary content hash mismatch"
            )

        if self.owner_uid != 0:
            raise ValueError(
                "canary owner uid must be root"
            )

        if self.owner_gid != 0:
            raise ValueError(
                "canary owner gid must be root"
            )

        if self.mode != 0o644:
            raise ValueError(
                "canary mode must be 0644"
            )

    def canonical_dict(self) -> dict:
        return {
            "destination": self.destination,
            "content_sha256": self.content_sha256,
            "owner_uid": self.owner_uid,
            "owner_gid": self.owner_gid,
            "mode": self.mode,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(
            self.canonical_dict()
        )


@dataclass(frozen=True, slots=True)
class CanarySystemdCommand:
    name: str
    argv: tuple[str, ...]
    mutation: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError(
                "command name required"
            )

        if not self.argv:
            raise ValueError(
                "argv required"
            )

        if self.argv[0] != SYSTEMCTL:
            raise ValueError(
                "only canonical systemctl allowed"
            )

        if "--no-ask-password" not in self.argv:
            raise ValueError(
                "--no-ask-password required"
            )

        joined = " ".join(self.argv)

        if "sudo" in joined or "pkexec" in joined:
            raise ValueError(
                "privilege wrapper forbidden"
            )

        if SENTINEL_UNIT in self.argv:
            raise ValueError(
                "Sentinel service mutation forbidden"
            )


@dataclass(frozen=True, slots=True)
class CanaryInstallationPlan:
    unit_name: str
    component_id: str
    design_fingerprint: str
    file_manifest: CanaryFileManifest

    install_commands: tuple[
        CanarySystemdCommand,
        ...,
    ]

    rollback_commands: tuple[
        CanarySystemdCommand,
        ...,
    ]

    def __post_init__(self) -> None:
        if self.unit_name != CANARY_UNIT:
            raise ValueError(
                "non-canonical canary unit"
            )

        if (
            self.component_id
            != "systemd:" + CANARY_UNIT
        ):
            raise ValueError(
                "non-canonical canary component"
            )

        if not self.design_fingerprint:
            raise ValueError(
                "design fingerprint required"
            )

        if not self.install_commands:
            raise ValueError(
                "installation commands required"
            )

        if not self.rollback_commands:
            raise ValueError(
                "rollback commands required"
            )

        for command in (
            self.install_commands
            + self.rollback_commands
        ):
            if SENTINEL_UNIT in command.argv:
                raise ValueError(
                    "Sentinel mutation forbidden"
                )

    def canonical_dict(self) -> dict:
        return {
            "unit_name": self.unit_name,
            "component_id": self.component_id,
            "design_fingerprint":
                self.design_fingerprint,

            "file_manifest":
                self.file_manifest.canonical_dict(),

            "file_manifest_fingerprint":
                self.file_manifest.fingerprint,

            "install_commands": [
                {
                    "name": command.name,
                    "argv": list(command.argv),
                    "mutation": command.mutation,
                }
                for command
                in self.install_commands
            ],

            "rollback_commands": [
                {
                    "name": command.name,
                    "argv": list(command.argv),
                    "mutation": command.mutation,
                }
                for command
                in self.rollback_commands
            ],
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(
            self.canonical_dict()
        )


@dataclass(frozen=True, slots=True)
class CanaryPreMutationGateResult:
    decision: str
    reason: str
    plan_fingerprint: str
    design_fingerprint: str
    privilege_result: str
    commander_approved: bool

    @property
    def ready(self) -> bool:
        return self.decision == "READY"


def build_canary_installation_plan(
    preflight: SystemdCanaryPreflight,
) -> CanaryInstallationPlan:
    if not isinstance(
        preflight,
        SystemdCanaryPreflight,
    ):
        raise TypeError(
            "preflight must be SystemdCanaryPreflight"
        )

    if not preflight.design_ready:
        raise RuntimeError(
            "canary design is not ready"
        )

    if preflight.fragment_collision:
        raise RuntimeError(
            "canary fragment collision"
        )

    if preflight.loaded_unit_collision:
        raise RuntimeError(
            "canary loaded-unit collision"
        )

    design = preflight.design

    manifest = CanaryFileManifest(
        destination=design.fragment_path,
        content=design.unit_text,
        content_sha256=design.unit_sha256,
        owner_uid=0,
        owner_gid=0,
        mode=0o644,
    )

    install_commands = (
        CanarySystemdCommand(
            name="daemon_reload",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "daemon-reload",
            ),
            mutation=True,
        ),

        CanarySystemdCommand(
            name="start_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "start",
                CANARY_UNIT,
            ),
            mutation=True,
        ),
    )

    rollback_commands = (
        CanarySystemdCommand(
            name="stop_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "stop",
                CANARY_UNIT,
            ),
            mutation=True,
        ),

        CanarySystemdCommand(
            name="daemon_reload_after_remove",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "daemon-reload",
            ),
            mutation=True,
        ),

        CanarySystemdCommand(
            name="reset_failed_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "reset-failed",
                CANARY_UNIT,
            ),
            mutation=True,
        ),
    )

    return CanaryInstallationPlan(
        unit_name=design.unit_name,
        component_id=design.component_id,
        design_fingerprint=(
            design.fingerprint
        ),
        file_manifest=manifest,
        install_commands=install_commands,
        rollback_commands=rollback_commands,
    )


def evaluate_canary_pre_mutation_gate(
    *,
    preflight: SystemdCanaryPreflight,
    plan: CanaryInstallationPlan,
    commander_approval: str | None,
) -> CanaryPreMutationGateResult:
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

    approved = (
        commander_approval
        == COMMANDER_INSTALL_APPROVAL
    )

    decision = "BLOCKED"
    reason = "unknown"

    if not preflight.design_ready:
        reason = "design_not_ready"

    elif preflight.fragment_collision:
        reason = "fragment_collision"

    elif preflight.loaded_unit_collision:
        reason = "loaded_unit_collision"

    elif (
        plan.design_fingerprint
        != preflight.design.fingerprint
    ):
        reason = "design_fingerprint_mismatch"

    elif (
        plan.file_manifest.content_sha256
        != preflight.design.unit_sha256
    ):
        reason = "unit_sha256_mismatch"

    elif (
        plan.file_manifest.destination
        != preflight.design.fragment_path
    ):
        reason = "fragment_path_mismatch"

    elif (
        preflight.privilege_result
        != "AUTHORIZED"
    ):
        reason = "privilege_not_authorized"

    elif not approved:
        reason = "commander_approval_required"

    else:
        decision = "READY"
        reason = "exact_canary_install_authorized"

    return CanaryPreMutationGateResult(
        decision=decision,
        reason=reason,
        plan_fingerprint=plan.fingerprint,
        design_fingerprint=(
            preflight.design.fingerprint
        ),
        privilege_result=(
            preflight.privilege_result
        ),
        commander_approved=approved,
    )
