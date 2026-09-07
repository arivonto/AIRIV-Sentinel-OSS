"""Generic resource-bound remediation model.

Phase 2.13D.D3.

This module binds resource identity, operation scope, effect identity,
and future permit identity. It does not execute remediation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sentinel.bound_effect_contract import BoundRemediationEffectContract

from sentinel.systemd_remediation_safety import (
    BoundSystemdActionScope,
    SystemdUnitSnapshot,
)


def _required(
    value: str,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field} must be str"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field} is required"
        )

    return value


def _canonical_hash(
    payload: dict,
) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@runtime_checkable
class ResourceIdentity(
    Protocol,
):
    @property
    def component_id(
        self,
    ) -> str:
        ...

    @property
    def fingerprint(
        self,
    ) -> str:
        ...

    @property
    def live_eligible(
        self,
    ) -> bool:
        ...


@dataclass(
    frozen=True,
    slots=True,
)
class GenericBoundRemediationEffect(BoundRemediationEffectContract):

    @property
    def policy_run_id(self) -> str:
        """Canonical policy run key for generic resource effects."""
        return self.run_id

    """Immutable exact resource-bound remediation effect."""

    run_id: str
    incident_id: str
    component_id: str

    resource_kind: str

    target: ResourceIdentity
    scope_fingerprint: str

    action: str
    argv: tuple[str, ...]

    execution_id: str
    permit_id: str

    def __post_init__(
        self,
    ) -> None:
        for field in (
            "run_id",
            "incident_id",
            "component_id",
            "resource_kind",
            "scope_fingerprint",
            "action",
            "execution_id",
            "permit_id",
        ):
            _required(
                getattr(
                    self,
                    field,
                ),
                field,
            )

        if not isinstance(
            self.target,
            ResourceIdentity,
        ):
            raise TypeError(
                "target does not satisfy ResourceIdentity"
            )

        if not self.target.live_eligible:
            raise ValueError(
                "target_not_live_eligible"
            )

        if (
            self.component_id
            != self.target.component_id
        ):
            raise ValueError(
                "component_target_mismatch"
            )

        if (
            not isinstance(
                self.argv,
                tuple,
            )
            or not self.argv
        ):
            raise ValueError(
                "argv must be non-empty tuple"
            )

        for item in self.argv:
            if (
                not isinstance(
                    item,
                    str,
                )
                or not item
            ):
                raise ValueError(
                    "argv items must be non-empty strings"
                )

    @property
    def target_fingerprint(
        self,
    ) -> str:
        return self.target.fingerprint

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "run_id":
                self.run_id,

            "incident_id":
                self.incident_id,

            "component_id":
                self.component_id,

            "resource_kind":
                self.resource_kind,

            "target_fingerprint":
                self.target_fingerprint,

            "scope_fingerprint":
                self.scope_fingerprint,

            "action":
                self.action,

            "argv":
                list(
                    self.argv
                ),

            "execution_id":
                self.execution_id,

            "permit_id":
                self.permit_id,
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict
        )

    @property
    def effect_fingerprint(
        self,
    ) -> str:
        """Compatibility name for the canonical immutable effect hash."""
        return self.fingerprint


@dataclass(
    frozen=True,
    slots=True,
)
class ResourceBoundPermitBinding:
    """Exact future permit envelope.

    This is binding evidence only. It does not claim the durable
    one-run permit.
    """

    run_id: str
    incident_id: str
    component_id: str

    resource_kind: str

    action: str

    execution_id: str
    permit_id: str

    target_fingerprint: str
    scope_fingerprint: str
    effect_fingerprint: str

    def __post_init__(
        self,
    ) -> None:
        for field in (
            "run_id",
            "incident_id",
            "component_id",
            "resource_kind",
            "action",
            "execution_id",
            "permit_id",
            "target_fingerprint",
            "scope_fingerprint",
            "effect_fingerprint",
        ):
            _required(
                getattr(
                    self,
                    field,
                ),
                field,
            )

    @classmethod
    def from_effect(
        cls,
        effect: GenericBoundRemediationEffect,
    ) -> "ResourceBoundPermitBinding":
        if not isinstance(
            effect,
            GenericBoundRemediationEffect,
        ):
            raise TypeError(
                "effect must be GenericBoundRemediationEffect"
            )

        return cls(
            run_id=effect.run_id,
            incident_id=effect.incident_id,
            component_id=effect.component_id,

            resource_kind=effect.resource_kind,

            action=effect.action,

            execution_id=effect.execution_id,
            permit_id=effect.permit_id,

            target_fingerprint=(
                effect.target_fingerprint
            ),

            scope_fingerprint=(
                effect.scope_fingerprint
            ),

            effect_fingerprint=(
                effect.fingerprint
            ),
        )

    def matches(
        self,
        effect: GenericBoundRemediationEffect,
    ) -> bool:
        expected = (
            ResourceBoundPermitBinding
            .from_effect(
                effect
            )
        )

        return self == expected

    @property
    def canonical_dict(
        self,
    ) -> dict:
        return {
            "run_id":
                self.run_id,

            "incident_id":
                self.incident_id,

            "component_id":
                self.component_id,

            "resource_kind":
                self.resource_kind,

            "action":
                self.action,

            "execution_id":
                self.execution_id,

            "permit_id":
                self.permit_id,

            "target_fingerprint":
                self.target_fingerprint,

            "scope_fingerprint":
                self.scope_fingerprint,

            "effect_fingerprint":
                self.effect_fingerprint,
        }

    @property
    def fingerprint(
        self,
    ) -> str:
        return _canonical_hash(
            self.canonical_dict
        )


@dataclass(
    frozen=True,
    slots=True,
)
class BoundSystemdRemediationPlan:
    """Canonical systemd resource-bound pre-execution plan."""

    before: SystemdUnitSnapshot

    scope: BoundSystemdActionScope

    effect: GenericBoundRemediationEffect

    permit_binding: ResourceBoundPermitBinding

    def __post_init__(
        self,
    ) -> None:
        if (
            self.before.identity.fingerprint
            != self.scope.target.fingerprint
        ):
            raise ValueError(
                "snapshot_scope_target_mismatch"
            )

        if (
            self.effect.target_fingerprint
            != self.scope.target.fingerprint
        ):
            raise ValueError(
                "effect_scope_target_mismatch"
            )

        if (
            self.effect.scope_fingerprint
            != self.scope.fingerprint
        ):
            raise ValueError(
                "effect_scope_fingerprint_mismatch"
            )

        if (
            self.effect.argv
            != self.scope.argv
        ):
            raise ValueError(
                "effect_argv_scope_mismatch"
            )

        if not self.permit_binding.matches(
            self.effect
        ):
            raise ValueError(
                "permit_binding_effect_mismatch"
            )


def build_bound_systemd_remediation_plan(
    *,
    before: SystemdUnitSnapshot,
    scope: BoundSystemdActionScope,

    run_id: str,
    incident_id: str,

    action: str,

    execution_id: str,
    permit_id: str,
) -> BoundSystemdRemediationPlan:
    """Construct one exact systemd pre-execution binding."""

    if not isinstance(
        before,
        SystemdUnitSnapshot,
    ):
        raise TypeError(
            "before must be SystemdUnitSnapshot"
        )

    if not isinstance(
        scope,
        BoundSystemdActionScope,
    ):
        raise TypeError(
            "scope must be BoundSystemdActionScope"
        )

    if (
        before.identity.fingerprint
        != scope.target.fingerprint
    ):
        raise ValueError(
            "snapshot_scope_target_mismatch"
        )

    if (
        before.active_state
        != scope.expected_pre_active_state
    ):
        raise ValueError(
            "unexpected_systemd_pre_state"
        )

    effect = (
        GenericBoundRemediationEffect(
            run_id=_required(
                run_id,
                "run_id",
            ),

            incident_id=_required(
                incident_id,
                "incident_id",
            ),

            component_id=(
                scope.component_id
            ),

            resource_kind=(
                "systemd.service"
            ),

            target=scope.target,

            scope_fingerprint=(
                scope.fingerprint
            ),

            action=_required(
                action,
                "action",
            ),

            argv=scope.argv,

            execution_id=_required(
                execution_id,
                "execution_id",
            ),

            permit_id=_required(
                permit_id,
                "permit_id",
            ),
        )
    )

    permit_binding = (
        ResourceBoundPermitBinding
        .from_effect(
            effect
        )
    )

    return BoundSystemdRemediationPlan(
        before=before,
        scope=scope,
        effect=effect,
        permit_binding=permit_binding,
    )


def configure_and_evaluate_bound_policy(
    *,
    policy,
    incident_state: str,
    effect: GenericBoundRemediationEffect,
):
    """Use the existing RemediationPolicy bound-effect authority.

    This function intentionally performs policy operations only.
    It does not claim a permit and does not execute argv.
    """

    if (
        effect.action
        not in policy.allowed_actions
    ):
        raise RuntimeError(
            "action_not_temporarily_allowed"
        )

    policy.configure_bound_effect(
        effect
    )

    return policy.evaluate_bound(
        incident_state=incident_state,
        effect=effect,
    )
