"""Immutable helper manifest for the bounded production pilot.

The manifest is pure data plus validation. It does not install files, write
polkit rules, call systemctl, or restart Sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from sentinel.bounded_pilot_readiness import (
    PILOT_ACTION,
    PILOT_HELPER_ID,
    PILOT_HELPER_SUBJECT,
    PILOT_UNIT,
)
from sentinel.systemd_canary_least_privilege import (
    POLKIT_ACTION_MANAGE_UNITS,
)


SENTINEL_USER = "arivonto"
SYSTEMCTL = "/usr/bin/systemctl"
HELPER_PATH = "/usr/local/libexec/airiv-sentinel-bounded-restart-helper"
POLKIT_RULE_PATH = (
    "/etc/polkit-1/rules.d/"
    "49-airiv-sentinel-bounded-pilot.rules"
)

HELPER_TEXT = """\
#!/usr/bin/env python3
import os
import sys

EXPECTED = ("RESTART", "airiv-sentinel.service")
SYSTEMCTL = "/usr/bin/systemctl"

if tuple(sys.argv[1:]) != EXPECTED:
    print("AIRIV bounded pilot helper denied: exact restart only", file=sys.stderr)
    sys.exit(64)

os.execv(
    SYSTEMCTL,
    (
        SYSTEMCTL,
        "--no-ask-password",
        "restart",
        "airiv-sentinel.service",
    ),
)
"""

POLKIT_RULE_TEXT = """\
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        action.lookup("unit") == "airiv-sentinel.service" &&
        action.lookup("verb") == "restart" &&
        subject.user == "arivonto" &&
        subject.system_unit == "airiv-sentinel.service" &&
        subject.no_new_privileges === true) {
        return polkit.Result.YES;
    }

    return polkit.Result.NOT_HANDLED;
});
"""


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
class BoundedPilotFileManifest:
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
            raise ValueError("bounded pilot files must be root-owned")
        if self.role == "helper" and self.mode != 0o755:
            raise ValueError("helper mode must be 0755")
        if self.role == "polkit_rule" and self.mode != 0o644:
            raise ValueError("polkit rule mode must be 0644")

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
class BoundedPilotHelperManifest:
    helper_id: str
    unit: str
    action: str
    subject_system_unit: str
    helper: BoundedPilotFileManifest
    polkit_rule: BoundedPilotFileManifest
    invocation_argv: tuple[str, ...]
    systemctl_argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.helper_id != PILOT_HELPER_ID:
            raise ValueError("helper identity mismatch")
        if self.unit != PILOT_UNIT:
            raise ValueError("pilot unit mismatch")
        if self.action != PILOT_ACTION:
            raise ValueError("pilot action mismatch")
        if self.subject_system_unit != PILOT_HELPER_SUBJECT:
            raise ValueError("pilot subject mismatch")
        if self.helper.destination != HELPER_PATH:
            raise ValueError("helper path mismatch")
        if self.helper.content != HELPER_TEXT:
            raise ValueError("helper content mismatch")
        if self.polkit_rule.destination != POLKIT_RULE_PATH:
            raise ValueError("polkit path mismatch")
        if self.polkit_rule.content != POLKIT_RULE_TEXT:
            raise ValueError("polkit content mismatch")
        if self.invocation_argv != (HELPER_PATH, PILOT_ACTION, PILOT_UNIT):
            raise ValueError("helper invocation argv mismatch")
        if self.systemctl_argv != (
            SYSTEMCTL,
            "--no-ask-password",
            "restart",
            PILOT_UNIT,
        ):
            raise ValueError("systemctl argv mismatch")

    def canonical_dict(self) -> dict:
        return {
            "helper_id": self.helper_id,
            "unit": self.unit,
            "action": self.action,
            "subject_system_unit": self.subject_system_unit,
            "helper": self.helper.canonical_dict(),
            "helper_fingerprint": self.helper.fingerprint,
            "polkit_rule": self.polkit_rule.canonical_dict(),
            "polkit_rule_fingerprint": self.polkit_rule.fingerprint,
            "invocation_argv": list(self.invocation_argv),
            "systemctl_argv": list(self.systemctl_argv),
        }

    @property
    def fingerprint(self) -> str:
        return _canonical_hash(self.canonical_dict())


@dataclass(frozen=True, slots=True)
class BoundedPilotHelperReadiness:
    helper_collision: bool
    polkit_collision: bool
    helper_content_matches: bool
    polkit_content_matches: bool
    helper_executable: bool
    polkit_rule_valid: bool
    subject_user: str
    subject_system_unit: str
    subject_no_new_privileges: bool

    @property
    def collision_free(self) -> bool:
        return not (self.helper_collision or self.polkit_collision)

    @property
    def installed_content_ready(self) -> bool:
        return (
            self.helper_content_matches
            and self.polkit_content_matches
            and self.helper_executable
            and self.polkit_rule_valid
        )

    @property
    def subject_ready(self) -> bool:
        return (
            self.subject_user == SENTINEL_USER
            and self.subject_system_unit == PILOT_HELPER_SUBJECT
            and self.subject_no_new_privileges is True
        )

    @property
    def activation_ready(self) -> bool:
        return (
            self.collision_free
            and self.installed_content_ready
            and self.subject_ready
        )


def canonical_bounded_pilot_helper_manifest() -> BoundedPilotHelperManifest:
    helper = BoundedPilotFileManifest(
        role="helper",
        destination=HELPER_PATH,
        content=HELPER_TEXT,
        content_sha256=_sha256_text(HELPER_TEXT),
        owner_uid=0,
        owner_gid=0,
        mode=0o755,
    )
    polkit_rule = BoundedPilotFileManifest(
        role="polkit_rule",
        destination=POLKIT_RULE_PATH,
        content=POLKIT_RULE_TEXT,
        content_sha256=_sha256_text(POLKIT_RULE_TEXT),
        owner_uid=0,
        owner_gid=0,
        mode=0o644,
    )
    return BoundedPilotHelperManifest(
        helper_id=PILOT_HELPER_ID,
        unit=PILOT_UNIT,
        action=PILOT_ACTION,
        subject_system_unit=PILOT_HELPER_SUBJECT,
        helper=helper,
        polkit_rule=polkit_rule,
        invocation_argv=(HELPER_PATH, PILOT_ACTION, PILOT_UNIT),
        systemctl_argv=(
            SYSTEMCTL,
            "--no-ask-password",
            "restart",
            PILOT_UNIT,
        ),
    )


def validate_bounded_pilot_polkit_rule(rule_text: str) -> bool:
    if rule_text != POLKIT_RULE_TEXT:
        return False
    required = (
        POLKIT_ACTION_MANAGE_UNITS,
        'action.lookup("unit") == "airiv-sentinel.service"',
        'action.lookup("verb") == "restart"',
        'subject.user == "arivonto"',
        'subject.system_unit == "airiv-sentinel.service"',
        "subject.no_new_privileges === true",
        "polkit.Result.YES",
        "polkit.Result.NOT_HANDLED",
    )
    forbidden = (
        "subject.isInGroup",
        "polkit.spawn",
        "sudo",
        "pkexec",
        '"start"',
        '"stop"',
        '"reload"',
        '"try-restart"',
        '"reload-or-restart"',
        "manage-unit-files",
    )
    return all(token in rule_text for token in required) and not any(
        token in rule_text for token in forbidden
    )
