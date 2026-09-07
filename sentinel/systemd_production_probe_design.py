"""Pure design manifest for the first production-remediation probe.

Phase 2.13D.D8.12B.

This module is descriptive only. It does not install systemd units,
modify polkit, configure RemediationPolicy, enable runtime layers,
issue activation grants, consume grants, or execute remediation.
"""

from dataclasses import dataclass
import hashlib


PROBE_UNIT = (
    "airiv-sentinel-production-remediation-probe.service"
)

PROBE_COMPONENT_ID = (
    "systemd:"
    + PROBE_UNIT
)

PROBE_FRAGMENT_PATH = (
    "/etc/systemd/system/"
    + PROBE_UNIT
)

PROBE_POLKIT_RULE_PATH = (
    "/etc/polkit-1/rules.d/"
    "49-airiv-sentinel-production-probe.rules"
)

PROBE_ACTION = "RESTART"

# First controlled production-policy target remains Commander-only.
PROBE_POLICY_MODE = "COMMANDER_ONLY"

# Conservative initial policy envelope.
PROBE_COOLDOWN_SECONDS = 3600.0
PROBE_RETRY_WINDOW_SECONDS = 86400.0
PROBE_MAX_ATTEMPTS = 1

# A machine activation grant must expire quickly.
PROBE_ACTIVATION_TTL_SECONDS = 300.0

PROBE_EFFECT_ARGV = (
    "/usr/bin/systemctl",
    "--no-ask-password",
    "restart",
    PROBE_UNIT,
)


PROBE_UNIT_TEXT = """[Unit]
Description=AIRIV Sentinel Production Remediation Probe

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
Restart=no
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
LockPersonality=yes
MemoryDenyWriteExecute=yes

[Install]
WantedBy=multi-user.target
"""


PROBE_POLKIT_RULE_TEXT = """polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.systemd1.manage-units" &&
        action.lookup("unit") == "airiv-sentinel-production-remediation-probe.service" &&
        action.lookup("verb") == "restart" &&
        subject.user == "arivonto" &&
        subject.system_unit == "airiv-sentinel.service" &&
        subject.no_new_privileges === true) {
        return polkit.Result.YES;
    }
    return polkit.Result.NOT_HANDLED;
});
"""


def _sha256(
    text,
):
    return hashlib.sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()


PROBE_UNIT_SHA256 = _sha256(
    PROBE_UNIT_TEXT
)

PROBE_POLKIT_RULE_SHA256 = _sha256(
    PROBE_POLKIT_RULE_TEXT
)


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdProductionProbeDesign:
    unit: str = PROBE_UNIT
    component_id: str = PROBE_COMPONENT_ID
    fragment_path: str = PROBE_FRAGMENT_PATH

    action: str = PROBE_ACTION
    policy_mode: str = PROBE_POLICY_MODE

    cooldown_seconds: float = (
        PROBE_COOLDOWN_SECONDS
    )

    retry_window_seconds: float = (
        PROBE_RETRY_WINDOW_SECONDS
    )

    max_attempts: int = (
        PROBE_MAX_ATTEMPTS
    )

    activation_ttl_seconds: float = (
        PROBE_ACTIVATION_TTL_SECONDS
    )

    unit_sha256: str = (
        PROBE_UNIT_SHA256
    )

    polkit_rule_path: str = (
        PROBE_POLKIT_RULE_PATH
    )

    polkit_rule_sha256: str = (
        PROBE_POLKIT_RULE_SHA256
    )

    def __post_init__(
        self,
    ) -> None:
        if self.unit != PROBE_UNIT:
            raise ValueError(
                "noncanonical probe unit"
            )

        if (
            self.component_id
            != "systemd:"
            + self.unit
        ):
            raise ValueError(
                "probe component mismatch"
            )

        if (
            self.fragment_path
            != "/etc/systemd/system/"
            + self.unit
        ):
            raise ValueError(
                "probe fragment mismatch"
            )

        if self.action != "RESTART":
            raise ValueError(
                "probe action must be RESTART"
            )

        if (
            self.policy_mode
            != "COMMANDER_ONLY"
        ):
            raise ValueError(
                "initial probe policy must be COMMANDER_ONLY"
            )

        if (
            type(self.max_attempts)
            is not int
            or self.max_attempts != 1
        ):
            raise ValueError(
                "initial probe max attempts must be one"
            )

        if (
            self.cooldown_seconds
            != 3600.0
            or self.retry_window_seconds
            != 86400.0
        ):
            raise ValueError(
                "noncanonical initial retry envelope"
            )

        if (
            self.activation_ttl_seconds
            != 300.0
        ):
            raise ValueError(
                "noncanonical activation ttl"
            )

        if (
            self.unit_sha256
            != PROBE_UNIT_SHA256
            or self.polkit_rule_sha256
            != PROBE_POLKIT_RULE_SHA256
        ):
            raise ValueError(
                "probe artifact fingerprint mismatch"
            )

    @property
    def future_policy_rule(
        self,
    ):
        return {
            "unit":
                self.unit,

            "action":
                self.action,

            "mode":
                self.policy_mode,

            "cooldown_seconds":
                self.cooldown_seconds,

            "retry_window_seconds":
                self.retry_window_seconds,

            "max_attempts":
                self.max_attempts,
        }

    @property
    def future_activation_requirements(
        self,
    ):
        return {
            "exact_incident_binding":
                True,

            "exact_component_binding":
                True,

            "exact_execution_binding":
                True,

            "exact_effect_fingerprint_binding":
                True,

            "durable_single_use_consumption":
                True,

            "ttl_seconds":
                self.activation_ttl_seconds,

            "commander_approval_required":
                True,
        }


def production_probe_design():
    return SystemdProductionProbeDesign()
