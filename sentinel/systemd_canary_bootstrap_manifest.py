"""Immutable planning contract for future canary bootstrap."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from sentinel.systemd_canary_least_privilege import (
    CANARY_POLKIT_RULE,
    POLKIT_RULE_PATH,
)
from sentinel.systemd_live_canary_preflight import (
    CANARY_FRAGMENT_PATH,
    CANARY_UNIT,
    CANARY_UNIT_TEXT,
)


SENTINEL_UNIT = "airiv-sentinel.service"

SENTINEL_DROPIN_PATH = (
    "/etc/systemd/system/"
    "airiv-sentinel.service.d/"
    "20-airiv-no-new-privileges.conf"
)

SENTINEL_DROPIN_TEXT = (
    "[Service]\n"
    "NoNewPrivileges=yes\n"
)

SYSTEMCTL = "/usr/bin/systemctl"

COMMANDER_SENTINEL_NNP_APPROVAL = (
    "APPROVE SENTINEL NNP RESTART 2.13D.D7C"
)

COMMANDER_CANARY_INSTALL_APPROVAL = (
    "APPROVE CANARY INSTALL 2.13D.D7C"
)


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _canonical_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class BootstrapFileManifest:
    role: str
    destination: str
    content: str
    content_sha256: str
    owner_uid: int
    owner_gid: int
    mode: int

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("role required")

        if not Path(self.destination).is_absolute():
            raise ValueError("destination must be absolute")

        if self.content_sha256 != _sha256_text(self.content):
            raise ValueError("content hash mismatch")

        if self.owner_uid != 0 or self.owner_gid != 0:
            raise ValueError("bootstrap files must be root-owned")

        if self.mode != 0o644:
            raise ValueError("bootstrap file mode must be 0644")

    def canonical_dict(self) -> dict:
        return {
            "role": self.role,
            "destination": self.destination,
            "content_sha256": self.content_sha256,
            "owner_uid": self.owner_uid,
            "owner_gid": self.owner_gid,
            "mode": self.mode,
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class BootstrapCommand:
    name: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("command name required")

        if not self.argv:
            raise ValueError("argv required")

        if self.argv[0] != SYSTEMCTL:
            raise ValueError("canonical systemctl required")

        if "--no-ask-password" not in self.argv:
            raise ValueError("--no-ask-password required")

        if any(token in {"sudo", "pkexec"} for token in self.argv):
            raise ValueError("privilege wrapper forbidden")


@dataclass(frozen=True, slots=True)
class CanaryBootstrapManifest:
    expected_pre_nnp: bool
    target_nnp: bool

    sentinel_dropin: BootstrapFileManifest
    canary_unit: BootstrapFileManifest
    polkit_rule: BootstrapFileManifest

    install_roles: tuple[str, ...]
    apply_commands: tuple[BootstrapCommand, ...]

    rollback_remove_paths: tuple[str, ...]
    rollback_commands: tuple[BootstrapCommand, ...]

    def __post_init__(self) -> None:
        if self.expected_pre_nnp:
            raise ValueError("canonical precondition must be NNP=false")

        if not self.target_nnp:
            raise ValueError("canonical target must be NNP=true")

        if self.sentinel_dropin.destination != SENTINEL_DROPIN_PATH:
            raise ValueError("Sentinel drop-in path mismatch")

        if self.sentinel_dropin.content != SENTINEL_DROPIN_TEXT:
            raise ValueError("Sentinel drop-in content mismatch")

        if self.canary_unit.destination != CANARY_FRAGMENT_PATH:
            raise ValueError("canary path mismatch")

        if self.canary_unit.content != CANARY_UNIT_TEXT:
            raise ValueError("canary content mismatch")

        if self.polkit_rule.destination != POLKIT_RULE_PATH:
            raise ValueError("polkit path mismatch")

        if self.polkit_rule.content != CANARY_POLKIT_RULE:
            raise ValueError("polkit content mismatch")

        if self.install_roles != (
            "sentinel_nnp_dropin",
            "canary_unit",
            "canary_polkit_rule",
        ):
            raise ValueError("install order mismatch")

        if self.rollback_remove_paths != (
            POLKIT_RULE_PATH,
            CANARY_FRAGMENT_PATH,
            SENTINEL_DROPIN_PATH,
        ):
            raise ValueError("rollback removal order mismatch")

    def canonical_dict(self) -> dict:
        return {
            "expected_pre_nnp": self.expected_pre_nnp,
            "target_nnp": self.target_nnp,
            "sentinel_dropin": self.sentinel_dropin.canonical_dict(),
            "sentinel_dropin_fingerprint":
                self.sentinel_dropin.fingerprint,
            "canary_unit": self.canary_unit.canonical_dict(),
            "canary_unit_fingerprint":
                self.canary_unit.fingerprint,
            "polkit_rule": self.polkit_rule.canonical_dict(),
            "polkit_rule_fingerprint":
                self.polkit_rule.fingerprint,
            "install_roles": list(self.install_roles),
            "apply_commands": [
                {
                    "name": command.name,
                    "argv": list(command.argv),
                }
                for command in self.apply_commands
            ],
            "rollback_remove_paths":
                list(self.rollback_remove_paths),
            "rollback_commands": [
                {
                    "name": command.name,
                    "argv": list(command.argv),
                }
                for command in self.rollback_commands
            ],
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class BootstrapReadiness:
    system_unit_supported: bool
    no_new_privileges_supported: bool

    current_nnp: bool

    dropin_collision: bool
    canary_collision: bool
    rule_collision: bool

    sentinel_approval: bool
    canary_approval: bool

    @property
    def capability_ready(self) -> bool:
        return (
            self.system_unit_supported
            and self.no_new_privileges_supported
        )

    @property
    def precondition_ready(self) -> bool:
        return self.current_nnp is False

    @property
    def collision_free(self) -> bool:
        return not (
            self.dropin_collision
            or self.canary_collision
            or self.rule_collision
        )

    @property
    def approvals_complete(self) -> bool:
        return (
            self.sentinel_approval
            and self.canary_approval
        )

    @property
    def mutation_ready(self) -> bool:
        return (
            self.capability_ready
            and self.precondition_ready
            and self.collision_free
            and self.approvals_complete
        )


def canonical_bootstrap_manifest() -> CanaryBootstrapManifest:
    dropin = BootstrapFileManifest(
        role="sentinel_nnp_dropin",
        destination=SENTINEL_DROPIN_PATH,
        content=SENTINEL_DROPIN_TEXT,
        content_sha256=_sha256_text(SENTINEL_DROPIN_TEXT),
        owner_uid=0,
        owner_gid=0,
        mode=0o644,
    )

    canary = BootstrapFileManifest(
        role="canary_unit",
        destination=CANARY_FRAGMENT_PATH,
        content=CANARY_UNIT_TEXT,
        content_sha256=_sha256_text(CANARY_UNIT_TEXT),
        owner_uid=0,
        owner_gid=0,
        mode=0o644,
    )

    rule = BootstrapFileManifest(
        role="canary_polkit_rule",
        destination=POLKIT_RULE_PATH,
        content=CANARY_POLKIT_RULE,
        content_sha256=_sha256_text(CANARY_POLKIT_RULE),
        owner_uid=0,
        owner_gid=0,
        mode=0o644,
    )

    apply = (
        BootstrapCommand(
            name="daemon_reload",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "daemon-reload",
            ),
        ),
        BootstrapCommand(
            name="restart_sentinel",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "restart",
                SENTINEL_UNIT,
            ),
        ),
        BootstrapCommand(
            name="start_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "start",
                CANARY_UNIT,
            ),
        ),
    )

    rollback = (
        BootstrapCommand(
            name="stop_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "stop",
                CANARY_UNIT,
            ),
        ),
        BootstrapCommand(
            name="daemon_reload_after_remove",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "daemon-reload",
            ),
        ),
        BootstrapCommand(
            name="restart_sentinel_after_restore",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "restart",
                SENTINEL_UNIT,
            ),
        ),
        BootstrapCommand(
            name="reset_failed_canary",
            argv=(
                SYSTEMCTL,
                "--no-ask-password",
                "reset-failed",
                CANARY_UNIT,
            ),
        ),
    )

    return CanaryBootstrapManifest(
        expected_pre_nnp=False,
        target_nnp=True,
        sentinel_dropin=dropin,
        canary_unit=canary,
        polkit_rule=rule,
        install_roles=(
            "sentinel_nnp_dropin",
            "canary_unit",
            "canary_polkit_rule",
        ),
        apply_commands=apply,
        rollback_remove_paths=(
            POLKIT_RULE_PATH,
            CANARY_FRAGMENT_PATH,
            SENTINEL_DROPIN_PATH,
        ),
        rollback_commands=rollback,
    )


def evaluate_bootstrap_readiness(
    *,
    system_unit_supported: bool,
    no_new_privileges_supported: bool,
    current_nnp: bool,
    dropin_collision: bool,
    canary_collision: bool,
    rule_collision: bool,
    sentinel_approval: str | None,
    canary_approval: str | None,
) -> BootstrapReadiness:
    return BootstrapReadiness(
        system_unit_supported=system_unit_supported,
        no_new_privileges_supported=no_new_privileges_supported,
        current_nnp=current_nnp,
        dropin_collision=dropin_collision,
        canary_collision=canary_collision,
        rule_collision=rule_collision,
        sentinel_approval=(
            sentinel_approval
            == COMMANDER_SENTINEL_NNP_APPROVAL
        ),
        canary_approval=(
            canary_approval
            == COMMANDER_CANARY_INSTALL_APPROVAL
        ),
    )
