"""Controlled-live pre-effect dry-run composition.

Phase 2.13C.1H.

This composition intentionally stops after exact Commander
authorization. It never enters Commander.remediate_bound().
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sentinel.isolated_tmux_live_validation import (
    IsolatedTmuxValidationSpec,
)
from sentinel.live_remediation_activation_lease import (
    TemporaryLiveRemediationActivationLease,
)
from sentinel.live_remediation_bound_composition import (
    BoundTmuxRemediationPlan,
    build_bound_tmux_remediation_plan,
)
from sentinel.live_remediation_commander_integration import (
    PreparedBoundTmuxRemediation,
    prepare_bound_tmux_remediation,
)
from sentinel.remediation_action_catalog import (
    RemediationActionEntry,
)


@dataclass(
    frozen=True,
    slots=True,
)
class ControlledLiveDryRunResult:
    workload_spec: IsolatedTmuxValidationSpec
    sensor_observation: dict[str, Any]
    incident: Any
    investigation: Any
    persisted_raw_evidence: dict[str, Any]
    plan: BoundTmuxRemediationPlan
    prepared: PreparedBoundTmuxRemediation

    @property
    def authorized(self) -> bool:
        return bool(
            getattr(
                self.prepared.authorization,
                "authorized",
                False,
            )
        )


def _require_mapping(
    value,
    field: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(
            f"{field} must be mapping"
        )

    return dict(value)


def _require_nonempty(
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


def _assert_fresh_safe_activation_state(
    runtime,
) -> None:
    if runtime.policy.allowed_actions != set():
        raise RuntimeError(
            "dry_run_requires_empty_policy"
        )

    if runtime.policy.list_bound_runs() != ():
        raise RuntimeError(
            "dry_run_requires_empty_bound_runs"
        )

    if (
        runtime.remediation_action_catalog
        .list_actions()
        != ()
    ):
        raise RuntimeError(
            "dry_run_requires_empty_catalog"
        )

    if (
        runtime.remediation_action_catalog
        .list_triggers()
        != ()
    ):
        raise RuntimeError(
            "dry_run_requires_empty_triggers"
        )


def _validate_observation_against_workload(
    *,
    observation: dict[str, Any],
    workload_spec: IsolatedTmuxValidationSpec,
) -> None:
    if observation.get("source") != "TMUX":
        raise ValueError(
            "dry_run_requires_tmux_observation"
        )

    if (
        observation.get(
            "tmux_identity_valid"
        )
        is not True
    ):
        raise ValueError(
            "dry_run_requires_strong_tmux_identity"
        )

    if "run_id" in observation:
        raise ValueError(
            "sensor_must_not_own_remediation_run_id"
        )

    if (
        observation.get(
            "server_socket"
        )
        != workload_spec.server_socket
    ):
        raise ValueError(
            "workload_sensor_socket_mismatch"
        )

    if (
        observation.get(
            "session_name"
        )
        != workload_spec.session_name
    ):
        raise ValueError(
            "workload_sensor_session_mismatch"
        )

    pane_id = observation.get(
        "pane_id"
    )

    if (
        not isinstance(pane_id, str)
        or not pane_id
    ):
        raise ValueError(
            "sensor_pane_id_required"
        )

    nested = observation.get(
        "tmux_identity"
    )

    if not isinstance(
        nested,
        Mapping,
    ):
        raise ValueError(
            "tmux_identity_snapshot_required"
        )

    for key in (
        "server_socket",
        "server_generation",
        "session_id",
        "session_name",
        "window_id",
        "pane_id",
    ):
        if nested.get(key) != observation.get(key):
            raise ValueError(
                "tmux_identity_snapshot_mismatch"
            )


def _persisted_observation(
    *,
    runtime,
    incident,
    investigation,
):
    records = tuple(
        incident.get_evidence_records()
    )

    if len(records) != 1:
        raise RuntimeError(
            "dry_run_requires_single_initial_evidence"
        )

    evidence_record = records[0]

    persisted = (
        runtime.diagnostic.store
        .get_observation(
            investigation.investigation_id,
            evidence_record.evidence_id,
        )
    )

    if persisted is None:
        raise RuntimeError(
            "persisted_observation_missing"
        )

    return persisted


def prepare_controlled_live_dry_run(
    *,
    runtime,
    workload_spec: IsolatedTmuxValidationSpec,
    sensor_observation,
    run_id: str,
    action: str,
    argv: tuple[str, ...],
    execution_id: str,
    permit_id: str,
    catalog_entry: RemediationActionEntry,
    trigger: str,
    reason: str = (
        "AIRIV Sentinel controlled-live dry-run"
    ),
) -> ControlledLiveDryRunResult:
    """Prepare exact live authorization and stop before execution."""

    if not isinstance(
        workload_spec,
        IsolatedTmuxValidationSpec,
    ):
        raise TypeError(
            "workload_spec must be IsolatedTmuxValidationSpec"
        )

    if not isinstance(
        catalog_entry,
        RemediationActionEntry,
    ):
        raise TypeError(
            "catalog_entry must be RemediationActionEntry"
        )

    observation = _require_mapping(
        sensor_observation,
        "sensor_observation",
    )

    _assert_fresh_safe_activation_state(
        runtime
    )

    _validate_observation_against_workload(
        observation=observation,
        workload_spec=workload_spec,
    )

    action = _require_nonempty(
        action,
        "action",
    )

    if catalog_entry.action != action:
        raise ValueError(
            "catalog_action_mismatch"
        )

    pane_id = observation["pane_id"]

    incident = (
        runtime.incident_manager
        .evaluate_anomaly(
            observation=observation,
            anomaly_type="PANE_DEAD",
            reason=reason,
        )
    )

    if incident.component_id != pane_id:
        raise RuntimeError(
            "incident_component_identity_mismatch"
        )

    investigation = (
        runtime.diagnostic
        .register_incident(
            incident
        )
    )

    if (
        investigation.component_id
        != pane_id
    ):
        raise RuntimeError(
            "investigation_component_identity_mismatch"
        )

    persisted = _persisted_observation(
        runtime=runtime,
        incident=incident,
        investigation=investigation,
    )

    if persisted.component_id != pane_id:
        raise RuntimeError(
            "persisted_component_identity_mismatch"
        )

    raw_evidence = _require_mapping(
        persisted.raw_evidence,
        "persisted.raw_evidence",
    )

    _validate_observation_against_workload(
        observation=raw_evidence,
        workload_spec=workload_spec,
    )

    plan = build_bound_tmux_remediation_plan(
        raw_evidence=raw_evidence,
        run_id=_require_nonempty(
            run_id,
            "run_id",
        ),
        incident_id=incident.incident_id,
        component_id=pane_id,
        action=action,
        argv=argv,
        execution_id=_require_nonempty(
            execution_id,
            "execution_id",
        ),
        permit_id=_require_nonempty(
            permit_id,
            "permit_id",
        ),
        expected_alive=True,
        timeout=5.0,
    )

    lease = (
        TemporaryLiveRemediationActivationLease(
            policy=runtime.policy,
            catalog=(
                runtime.remediation_action_catalog
            ),
            effect=plan.effect,
            entry=catalog_entry,
            trigger=_require_nonempty(
                trigger,
                "trigger",
            ),
        )
    )

    # HARD SAFETY BOUNDARY:
    # Authorization is created while the exact temporary activation
    # lease exists. The lease is restored before returning.
    #
    # No remediate_bound(), no permit, no execution.
    with lease:
        prepared = (
            prepare_bound_tmux_remediation(
                commander=runtime.commander,
                incident=incident,
                plan=plan,
            )
        )

        if not prepared.authorization.authorized:
            raise RuntimeError(
                "dry_run_authorization_denied"
            )

        if not prepared.authorization.matches(
            plan.effect
        ):
            raise RuntimeError(
                "dry_run_authorization_effect_mismatch"
            )

    # Prove temporary activation is completely gone.
    _assert_fresh_safe_activation_state(
        runtime
    )

    return ControlledLiveDryRunResult(
        workload_spec=workload_spec,
        sensor_observation=observation,
        incident=incident,
        investigation=investigation,
        persisted_raw_evidence=raw_evidence,
        plan=plan,
        prepared=prepared,
    )
