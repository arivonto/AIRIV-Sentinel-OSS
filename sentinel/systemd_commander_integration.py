"""Systemd Commander integration.

Phase 2.13D.D5B.

This module owns no policy, permit, execution, lifecycle, or systemd
mutation authority. It composes already-canonical authorities and
performs independent post-effect verification.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from sentinel.systemd_production_runtime_guard import (
    SystemdProductionAttemptRecord, production_runtime_guard,
)

from sentinel.commander import CommanderOrchestrator
from sentinel.generic_execution_permit_adapter import (
    GenericResourceExecutionPermitAdapter,
)
from sentinel.live_remediation_safety import (
    BoundRemediationAuthorization,
)
from sentinel.remediation_execution_identity import (
    ExecutionIdentityRecord,
)
from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.execution import (
    ExecutionResult,
)
from sentinel.systemd_remediation_safety import (
    SystemdRestartVerification,
    SystemdRestartVerifier,
    SystemdUnitSnapshot,
)

if TYPE_CHECKING:
    from sentinel.systemd_production_commander_authorization import (
        SystemdProductionCommanderAuthorizationContext,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdCommanderIntegrationResult:
    authorization: BoundRemediationAuthorization

    execution: ExecutionResult | None
    identity_record: ExecutionIdentityRecord | None

    replayed: bool

    after: SystemdUnitSnapshot | None
    verification: SystemdRestartVerification | None

    @property
    def execution_succeeded(
        self,
    ) -> bool:
        return bool(
            self.execution is not None
            and self.execution.success
        )

    @property
    def verification_succeeded(
        self,
    ) -> bool:
        return bool(
            self.verification is not None
            and self.verification.verified
        )

    @property
    def recovered(
        self,
    ) -> bool:
        return (
            self.authorization.authorized
            and self.execution_succeeded
            and self.verification_succeeded
        )


class SystemdCommanderIntegration:
    """Compose systemd remediation through canonical Commander owners."""

    def __init__(
        self,
        commander: CommanderOrchestrator,
        *,
        verifier: SystemdRestartVerifier | None = None,
    ) -> None:
        if not isinstance(
            commander,
            CommanderOrchestrator,
        ):
            raise TypeError(
                "commander must be a CommanderOrchestrator"
            )

        if (
            verifier is not None
            and not isinstance(
                verifier,
                SystemdRestartVerifier,
            )
        ):
            raise TypeError(
                "verifier must be a SystemdRestartVerifier"
            )

        self.commander = commander

        self.verifier = (
            verifier
            or SystemdRestartVerifier()
        )

        orchestrator = (
            commander.remediation_orchestrator
        )

        self.policy = orchestrator.policy

        self.execution_adapter = (
            GenericResourceExecutionPermitAdapter(
                orchestrator.identity_boundary
            )
        )

    # PHASE_213D_D8_3_PRODUCTION_POLICY_WIRING
    def execute_verified(
        self,
        *,
        plan: BoundSystemdRemediationPlan,
        incident_state: str,
        after_snapshot_provider:
            Callable[[], SystemdUnitSnapshot],
        timeout: float = 5.0,
        production_now: float | None = None,
        production_attempts=(),
        active_production_effects: int = 0,
        commander_authorization: SystemdProductionCommanderAuthorizationContext | None = None,
    ) -> SystemdCommanderIntegrationResult:
        if not isinstance(
            plan,
            BoundSystemdRemediationPlan,
        ):
            raise TypeError(
                "plan must be a BoundSystemdRemediationPlan"
            )

        if (
            not isinstance(
                incident_state,
                str,
            )
            or not incident_state.strip()
        ):
            raise ValueError(
                "incident_state is required"
            )

        if not callable(
            after_snapshot_provider
        ):
            raise TypeError(
                "after_snapshot_provider must be callable"
            )

        if commander_authorization is not None:
            from sentinel.systemd_production_commander_authorization import (
                SystemdProductionCommanderAuthorizationContext,
            )

            if (
                type(commander_authorization)
                is not SystemdProductionCommanderAuthorizationContext
            ):
                raise TypeError(
                    "canonical Commander authorization context required"
                )

            if production_now is None:
                raise ValueError(
                    "Commander authorization requires production evaluation"
                )

        guard = (production_runtime_guard() if production_now is not None
                 else nullcontext(None))
        with guard as production:
            if production is None:
                authorization = self.policy.evaluate_bound(
                    incident_state=incident_state.strip(), effect=plan.effect,
                )
            else:
                ledger, acquired, durable_attempts = production
                authorization = self.policy.evaluate_systemd_production_bound(
                    incident_state=incident_state.strip(),
                    effect=plan.effect,
                    now=production_now,
                    attempts=durable_attempts + tuple(production_attempts),
                    active_production_effects=(
                        active_production_effects if acquired else 1
                    ),
                    commander_authorization=commander_authorization,
                )[0]

            if not authorization.authorized:
                return (
                    SystemdCommanderIntegrationResult(
                        authorization=authorization,

                        execution=None,
                        identity_record=None,

                        replayed=False,

                        after=None,
                        verification=None,
                    )
                )

            if production is not None:
                ledger.append(SystemdProductionAttemptRecord.from_plan(
                    plan, production_now,
                ))

            execution_result = (
                self.execution_adapter.execute(
                    effect=plan.effect,

                    authorization=authorization,

                    permit_binding=(
                        plan.permit_binding
                    ),

                    incident_state=(
                        incident_state.strip()
                    ),

                    timeout=timeout,
                )
            )

            execution = (
                execution_result.execution
            )

            # Execution success is not recovery.
            # Do not perform a post-state recovery assertion after a
            # failed or indeterminate execution.
            if (
                execution is None
                or not execution.success
            ):
                return (
                    SystemdCommanderIntegrationResult(
                        authorization=authorization,

                        execution=execution,

                        identity_record=(
                            execution_result
                            .identity_record
                        ),

                        replayed=(
                            execution_result.replayed
                        ),

                        after=None,
                        verification=None,
                    )
                )

            # Independent observation boundary.
            after = (
                after_snapshot_provider()
            )

            if not isinstance(
                after,
                SystemdUnitSnapshot,
            ):
                raise TypeError(
                    "after_snapshot_provider must return "
                    "SystemdUnitSnapshot"
                )

            verification = (
                self.verifier.verify(
                    scope=plan.scope,
                    before=plan.before,
                    after=after,
                )
            )

            return (
                SystemdCommanderIntegrationResult(
                    authorization=authorization,

                    execution=execution,

                    identity_record=(
                        execution_result
                        .identity_record
                    ),

                    replayed=(
                        execution_result.replayed
                    ),

                    after=after,

                    verification=verification,
                )
            )
