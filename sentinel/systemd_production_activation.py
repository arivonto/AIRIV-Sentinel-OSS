"""Pure controlled-activation value contract for production systemd remediation.

Phase 2.13D.D8.10A.

This module defines activation evidence only.

It does not enable runtime layers, authorize remediation, delegate,
execute, mutate durable state, or affect the host.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass


_ID_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
)


def _required_id(
    value,
    name,
):
    if (
        type(value) is not str
        or _ID_RE.fullmatch(value) is None
    ):
        raise ValueError(
            f"invalid_{name}"
        )

    return value


def _finite_non_negative(
    value,
    name,
):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(
            f"{name} must be finite and non-negative"
        )

    return float(value)


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdProductionActivationGrant:
    """Immutable activation evidence.

    This value is not policy authorization and does not alter runtime state.
    """

    activation_id: str
    approval_id: str

    incident_id: str
    component_id: str
    execution_id: str
    effect_fingerprint: str

    issued_at: float
    expires_at: float

    def __post_init__(
        self,
    ) -> None:
        _required_id(
            self.activation_id,
            "activation_id",
        )

        _required_id(
            self.approval_id,
            "approval_id",
        )

        for name in (
            "incident_id",
            "component_id",
            "execution_id",
            "effect_fingerprint",
        ):
            value = getattr(
                self,
                name,
            )

            if (
                type(value) is not str
                or not value.strip()
            ):
                raise ValueError(
                    f"{name} is required"
                )

        issued_at = _finite_non_negative(
            self.issued_at,
            "issued_at",
        )

        expires_at = _finite_non_negative(
            self.expires_at,
            "expires_at",
        )

        if expires_at <= issued_at:
            raise ValueError(
                "activation expiry must be after issuance"
            )

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "activation_id":
                self.activation_id,

            "approval_id":
                self.approval_id,

            "incident_id":
                self.incident_id,

            "component_id":
                self.component_id,

            "execution_id":
                self.execution_id,

            "effect_fingerprint":
                self.effect_fingerprint,

            "issued_at":
                float(
                    self.issued_at
                ),

            "expires_at":
                float(
                    self.expires_at
                ),
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        encoded = json.dumps(
            self.canonical_dict,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            encoded
        ).hexdigest()

    def is_active(
        self,
        now,
    ) -> bool:
        current = _finite_non_negative(
            now,
            "now",
        )

        return (
            self.issued_at
            <= current
            < self.expires_at
        )

    def matches_effect(
        self,
        *,
        incident_id,
        component_id,
        execution_id,
        effect_fingerprint,
    ) -> bool:
        return (
            self.incident_id
            == incident_id
            and self.component_id
            == component_id
            and self.execution_id
            == execution_id
            and self.effect_fingerprint
            == effect_fingerprint
        )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdProductionActivationAssessment:
    eligible: bool
    reason: str
    activation_fingerprint: str | None


class SystemdProductionActivationBoundary:
    """Pure validation of one explicit activation grant."""

    def assess(
        self,
        *,
        grant: SystemdProductionActivationGrant,
        now: float,
        incident_id: str,
        component_id: str,
        execution_id: str,
        effect_fingerprint: str,
    ) -> SystemdProductionActivationAssessment:
        if (
            type(grant)
            is not SystemdProductionActivationGrant
        ):
            raise TypeError(
                "SystemdProductionActivationGrant required"
            )

        current = _finite_non_negative(
            now,
            "now",
        )

        if not grant.is_active(
            current
        ):
            return SystemdProductionActivationAssessment(
                eligible=False,
                reason="activation_not_active",
                activation_fingerprint=(
                    grant.fingerprint
                ),
            )

        if not grant.matches_effect(
            incident_id=incident_id,
            component_id=component_id,
            execution_id=execution_id,
            effect_fingerprint=effect_fingerprint,
        ):
            return SystemdProductionActivationAssessment(
                eligible=False,
                reason="activation_effect_binding_mismatch",
                activation_fingerprint=(
                    grant.fingerprint
                ),
            )

        return SystemdProductionActivationAssessment(
            eligible=True,
            reason="activation_binding_valid",
            activation_fingerprint=(
                grant.fingerprint
            ),
        )
