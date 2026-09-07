"""Least-privilege authorization design for systemd canary remediation.

Phase 2.13D.D7C.3.

Pure planning and validation. No host mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


POLKIT_ACTION_MANAGE_UNITS = (
    "org.freedesktop.systemd1.manage-units"
)

POLKIT_RULE_PATH = (
    "/etc/polkit-1/rules.d/"
    "49-airiv-sentinel-canary.rules"
)

SENTINEL_USER = "arivonto"

SENTINEL_UNIT = (
    "airiv-sentinel.service"
)

CANARY_UNIT = (
    "airiv-sentinel-remediation-canary.service"
)

CANARY_VERB = "restart"


CANARY_POLKIT_RULE = """\
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        action.lookup("unit") == "airiv-sentinel-remediation-canary.service" &&
        action.lookup("verb") == "restart" &&
        subject.user == "arivonto" &&
        subject.system_unit == "airiv-sentinel.service" &&
        subject.no_new_privileges === true) {
        return polkit.Result.YES;
    }

    return polkit.Result.NOT_HANDLED;
});
"""


def _canonical_hash(
    payload: dict,
) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(
        encoded
    ).hexdigest()


@dataclass(
    frozen=True,
    slots=True,
)
class CanaryPolkitRequest:
    action_id: str
    unit: str
    verb: str
    user: str
    system_unit: str
    no_new_privileges: bool


@dataclass(
    frozen=True,
    slots=True,
)
class CanaryPolkitAuthorizationDesign:
    rule_path: str
    rule_text: str
    rule_sha256: str
    owner_uid: int
    owner_gid: int
    mode: int

    action_id: str
    unit: str
    verb: str
    user: str
    system_unit: str
    require_no_new_privileges: bool

    def __post_init__(
        self,
    ) -> None:
        if self.rule_path != POLKIT_RULE_PATH:
            raise ValueError(
                "non-canonical polkit rule path"
            )

        if self.rule_text != CANARY_POLKIT_RULE:
            raise ValueError(
                "non-canonical polkit rule text"
            )

        expected_hash = sha256(
            self.rule_text.encode(
                "utf-8"
            )
        ).hexdigest()

        if self.rule_sha256 != expected_hash:
            raise ValueError(
                "polkit rule hash mismatch"
            )

        if self.owner_uid != 0:
            raise ValueError(
                "polkit rule owner must be root"
            )

        if self.owner_gid != 0:
            raise ValueError(
                "polkit rule group must be root"
            )

        if self.mode != 0o644:
            raise ValueError(
                "polkit rule mode must be 0644"
            )

        if (
            self.action_id
            != POLKIT_ACTION_MANAGE_UNITS
        ):
            raise ValueError(
                "invalid polkit action"
            )

        if self.unit != CANARY_UNIT:
            raise ValueError(
                "authorization must be canary-only"
            )

        if self.verb != CANARY_VERB:
            raise ValueError(
                "authorization must be restart-only"
            )

        if self.user != SENTINEL_USER:
            raise ValueError(
                "authorization user mismatch"
            )

        if self.system_unit != SENTINEL_UNIT:
            raise ValueError(
                "authorization system-unit mismatch"
            )

        if not self.require_no_new_privileges:
            raise ValueError(
                "NoNewPrivileges requirement cannot be disabled"
            )

    def canonical_dict(
        self,
    ) -> dict:
        return {
            "rule_path":
                self.rule_path,

            "rule_sha256":
                self.rule_sha256,

            "owner_uid":
                self.owner_uid,

            "owner_gid":
                self.owner_gid,

            "mode":
                self.mode,

            "action_id":
                self.action_id,

            "unit":
                self.unit,

            "verb":
                self.verb,

            "user":
                self.user,

            "system_unit":
                self.system_unit,

            "require_no_new_privileges":
                self.require_no_new_privileges,
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict()
        )

    def authorizes(
        self,
        request: CanaryPolkitRequest,
    ) -> bool:
        if not isinstance(
            request,
            CanaryPolkitRequest,
        ):
            raise TypeError(
                "request must be CanaryPolkitRequest"
            )

        return (
            request.action_id
            == self.action_id

            and request.unit
            == self.unit

            and request.verb
            == self.verb

            and request.user
            == self.user

            and request.system_unit
            == self.system_unit

            and request.no_new_privileges
            is True
        )


@dataclass(
    frozen=True,
    slots=True,
)
class CanaryAuthorizationReadiness:
    design: CanaryPolkitAuthorizationDesign

    sentinel_user: str

    sentinel_no_new_privileges: bool

    rule_collision: bool

    canary_fragment_collision: bool

    current_privilege: str

    rule_offline_valid: bool

    @property
    def subject_ready(
        self,
    ) -> bool:
        return (
            self.sentinel_user
            == self.design.user

            and self.sentinel_no_new_privileges
        )

    @property
    def bootstrap_collision_free(
        self,
    ) -> bool:
        return (
            not self.rule_collision
            and not self.canary_fragment_collision
        )

    @property
    def design_ready(
        self,
    ) -> bool:
        return (
            self.rule_offline_valid
            and self.bootstrap_collision_free
        )

    @property
    def runtime_authorization_ready(
        self,
    ) -> bool:
        # D7C.3 must never infer a future installed rule
        # from planning data alone.
        return (
            self.design_ready
            and self.subject_ready
            and self.current_privilege
            == "AUTHORIZED"
        )

    @property
    def fail_closed(
        self,
    ) -> bool:
        return (
            not self.runtime_authorization_ready
        )


def canonical_authorization_design(
) -> CanaryPolkitAuthorizationDesign:
    return CanaryPolkitAuthorizationDesign(
        rule_path=POLKIT_RULE_PATH,

        rule_text=CANARY_POLKIT_RULE,

        rule_sha256=sha256(
            CANARY_POLKIT_RULE.encode(
                "utf-8"
            )
        ).hexdigest(),

        owner_uid=0,
        owner_gid=0,
        mode=0o644,

        action_id=(
            POLKIT_ACTION_MANAGE_UNITS
        ),

        unit=CANARY_UNIT,
        verb=CANARY_VERB,
        user=SENTINEL_USER,
        system_unit=SENTINEL_UNIT,

        require_no_new_privileges=True,
    )


def validate_canary_polkit_rule(
    rule_text: str,
) -> bool:
    if rule_text != CANARY_POLKIT_RULE:
        return False

    required = (
        'polkit.addRule(function(action, subject)',
        (
            'action.id == '
            '"org.freedesktop.systemd1.manage-units"'
        ),
        (
            'action.lookup("unit") == '
            '"airiv-sentinel-remediation-canary.service"'
        ),
        (
            'action.lookup("verb") == '
            '"restart"'
        ),
        (
            'subject.user == '
            '"arivonto"'
        ),
        (
            'subject.system_unit == '
            '"airiv-sentinel.service"'
        ),
        (
            'subject.no_new_privileges === true'
        ),
        (
            'return polkit.Result.YES;'
        ),
        (
            'return polkit.Result.NOT_HANDLED;'
        ),
    )

    for token in required:
        if token not in rule_text:
            return False

    forbidden = (
        "manage-unit-files",
        "reload-daemon",
        '"start"',
        '"stop"',
        '"reload"',
        '"try-restart"',
        '"reload-or-restart"',
        "subject.isInGroup",
        "polkit.Result.AUTH_ADMIN",
        "polkit.Result.AUTH_SELF",
        "polkit.spawn",
        "sudo",
        "pkexec",
        "=>",
        "let ",
        "const ",
    )

    for token in forbidden:
        if token in rule_text:
            return False

    if (
        rule_text.count(
            "polkit.Result.YES"
        )
        != 1
    ):
        return False

    if (
        rule_text.count(
            "polkit.Result.NOT_HANDLED"
        )
        != 1
    ):
        return False

    if (
        rule_text.count("{")
        != rule_text.count("}")
    ):
        return False

    if (
        rule_text.count("(")
        != rule_text.count(")")
    ):
        return False

    return True
