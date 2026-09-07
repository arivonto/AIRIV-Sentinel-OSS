"""Production systemd remediation target-safety policy.

This module is deliberately side-effect free.

It owns target-safety facts only.  It does not own the canonical
RemediationPolicy ALLOW/DENY decision and cannot execute remediation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from types import MappingProxyType
from typing import Iterable, Mapping


ACTION_RESTART = "RESTART"

_UNIT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*\.service$")


class ProductionTargetMode(str, Enum):
    AUTONOMOUS = "AUTONOMOUS"
    COMMANDER_ONLY = "COMMANDER_ONLY"


@dataclass(frozen=True)
class SystemdAttemptFact:
    unit: str
    action: str
    timestamp: float


@dataclass(frozen=True)
class SystemdVerificationRequirements:
    require_loaded: bool = True
    require_active: bool = True
    require_invocation_id_change: bool = True


@dataclass(frozen=True)
class SystemdProductionTargetRule:
    unit: str
    mode: ProductionTargetMode
    cooldown_seconds: float = 300.0
    retry_window_seconds: float = 900.0
    max_attempts_per_window: int = 1
    verification: SystemdVerificationRequirements = (
        SystemdVerificationRequirements()
    )

    def __post_init__(self) -> None:
        validate_unit_name(self.unit)

        if self.mode not in (
            ProductionTargetMode.AUTONOMOUS,
            ProductionTargetMode.COMMANDER_ONLY,
        ):
            raise ValueError("invalid production target mode")

        if (
            type(self.cooldown_seconds) not in (int, float)
            or not math.isfinite(self.cooldown_seconds)
            or self.cooldown_seconds <= 0
        ):
            raise ValueError("cooldown_seconds must be finite and positive")

        if (
            type(self.retry_window_seconds) not in (int, float)
            or not math.isfinite(self.retry_window_seconds)
            or self.retry_window_seconds <= 0
        ):
            raise ValueError(
                "retry_window_seconds must be finite and positive"
            )

        if (
            type(self.max_attempts_per_window) is not int
            or self.max_attempts_per_window <= 0
        ):
            raise ValueError(
                "max_attempts_per_window must be a positive integer"
            )

        verification = self.verification

        if type(verification) is not SystemdVerificationRequirements:
            raise TypeError(
                "verification must be SystemdVerificationRequirements"
            )

        if not (
            verification.require_loaded
            and verification.require_active
            and verification.require_invocation_id_change
        ):
            raise ValueError(
                "production systemd verification requirements "
                "cannot be weakened"
            )


@dataclass(frozen=True)
class SystemdProductionTargetAssessment:
    unit: str
    action: str

    target_known: bool
    protected_target: bool

    autonomous_eligible: bool
    commander_required: bool

    cooldown_satisfied: bool
    retry_budget_available: bool
    blast_radius_available: bool

    reasons: tuple[str, ...]

    verification: SystemdVerificationRequirements | None


PROTECTED_EXACT_UNITS = frozenset(
    {
        "airiv-sentinel.service",
        "airiv-sentinel-remediation-canary.service",
        "dbus.service",
        "polkit.service",
        "ssh.service",
        "sshd.service",
        "NetworkManager.service",
        "networking.service",
        "ufw.service",
        "firewalld.service",
        "nftables.service",
    }
)

PROTECTED_PREFIXES = (
    "systemd-",
)


def validate_unit_name(unit: str) -> str:
    if type(unit) is not str:
        raise TypeError("unit must be str")

    if not unit or unit != unit.strip():
        raise ValueError("unit must be non-empty and canonical")

    if any(token in unit for token in ("*", "?", "[", "]", "{", "}")):
        raise ValueError("wildcards/globs are prohibited")

    if "@" in unit:
        raise ValueError("systemd template units are prohibited in V1")

    if not _UNIT_RE.fullmatch(unit):
        raise ValueError("V1 supports exact .service unit names only")

    return unit


def protected_target(unit: str) -> bool:
    validate_unit_name(unit)

    if unit in PROTECTED_EXACT_UNITS:
        return True

    return any(unit.startswith(prefix) for prefix in PROTECTED_PREFIXES)


class SystemdProductionTargetPolicy:
    """Pure target-safety assessment for real production services.

    Default construction contains zero production targets.
    """

    def __init__(
        self,
        rules: Iterable[SystemdProductionTargetRule] = (),
    ) -> None:
        materialized: dict[str, SystemdProductionTargetRule] = {}

        for rule in rules:
            if type(rule) is not SystemdProductionTargetRule:
                raise TypeError(
                    "rules must contain SystemdProductionTargetRule"
                )

            if protected_target(rule.unit):
                raise ValueError(
                    f"protected target cannot be allowlisted: {rule.unit}"
                )

            if rule.unit in materialized:
                raise ValueError(
                    f"duplicate production target rule: {rule.unit}"
                )

            materialized[rule.unit] = rule

        self._rules: Mapping[str, SystemdProductionTargetRule] = (
            MappingProxyType(materialized)
        )

    @property
    def rules(self) -> Mapping[str, SystemdProductionTargetRule]:
        return self._rules

    def assess(
        self,
        *,
        unit: str,
        action: str,
        now: float,
        attempts: Iterable[SystemdAttemptFact] = (),
        active_production_effects: int = 0,
    ) -> SystemdProductionTargetAssessment:
        validate_unit_name(unit)

        if type(action) is not str:
            raise TypeError("action must be str")

        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("now must be finite")

        if now < 0:
            raise ValueError("now must be non-negative")

        if (
            type(active_production_effects) is not int
            or active_production_effects < 0
        ):
            raise ValueError(
                "active_production_effects must be non-negative int"
            )

        if action != ACTION_RESTART:
            return SystemdProductionTargetAssessment(
                unit=unit,
                action=action,
                target_known=unit in self._rules,
                protected_target=protected_target(unit),
                autonomous_eligible=False,
                commander_required=False,
                cooldown_satisfied=False,
                retry_budget_available=False,
                blast_radius_available=(
                    active_production_effects == 0
                ),
                reasons=("unsupported_action",),
                verification=None,
            )

        if protected_target(unit):
            return SystemdProductionTargetAssessment(
                unit=unit,
                action=action,
                target_known=False,
                protected_target=True,
                autonomous_eligible=False,
                commander_required=False,
                cooldown_satisfied=False,
                retry_budget_available=False,
                blast_radius_available=(
                    active_production_effects == 0
                ),
                reasons=("protected_target",),
                verification=None,
            )

        rule = self._rules.get(unit)

        if rule is None:
            return SystemdProductionTargetAssessment(
                unit=unit,
                action=action,
                target_known=False,
                protected_target=False,
                autonomous_eligible=False,
                commander_required=False,
                cooldown_satisfied=False,
                retry_budget_available=False,
                blast_radius_available=(
                    active_production_effects == 0
                ),
                reasons=("target_not_allowlisted",),
                verification=None,
            )

        relevant: list[SystemdAttemptFact] = []

        for attempt in attempts:
            if type(attempt) is not SystemdAttemptFact:
                raise TypeError(
                    "attempts must contain SystemdAttemptFact"
                )

            if (
                type(attempt.timestamp) not in (int, float)
                or not math.isfinite(attempt.timestamp)
                or attempt.timestamp < 0
            ):
                raise ValueError("attempt timestamp must be finite")

            if attempt.timestamp > now:
                raise ValueError(
                    "future attempt timestamp is invalid"
                )

            if attempt.unit == unit and attempt.action == action:
                relevant.append(attempt)

        last_timestamp = max(
            (attempt.timestamp for attempt in relevant),
            default=None,
        )

        cooldown_satisfied = (
            last_timestamp is None
            or now - last_timestamp >= rule.cooldown_seconds
        )

        window_floor = now - rule.retry_window_seconds

        attempts_in_window = sum(
            1
            for attempt in relevant
            if attempt.timestamp >= window_floor
        )

        retry_budget_available = (
            attempts_in_window < rule.max_attempts_per_window
        )

        blast_radius_available = active_production_effects == 0

        commander_required = (
            rule.mode is ProductionTargetMode.COMMANDER_ONLY
        )

        reasons: list[str] = []

        if commander_required:
            reasons.append("commander_required")

        if not cooldown_satisfied:
            reasons.append("cooldown_active")

        if not retry_budget_available:
            reasons.append("retry_budget_exhausted")

        if not blast_radius_available:
            reasons.append("production_effect_already_active")

        autonomous_eligible = bool(
            rule.mode is ProductionTargetMode.AUTONOMOUS
            and cooldown_satisfied
            and retry_budget_available
            and blast_radius_available
        )

        if autonomous_eligible:
            reasons.append("autonomous_target_safety_satisfied")

        return SystemdProductionTargetAssessment(
            unit=unit,
            action=action,
            target_known=True,
            protected_target=False,
            autonomous_eligible=autonomous_eligible,
            commander_required=commander_required,
            cooldown_satisfied=cooldown_satisfied,
            retry_budget_available=retry_budget_available,
            blast_radius_available=blast_radius_available,
            reasons=tuple(reasons),
            verification=rule.verification,
        )
