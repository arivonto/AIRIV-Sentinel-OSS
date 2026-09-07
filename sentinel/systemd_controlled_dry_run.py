"""Systemd controlled dry-run — Phase 2.13D.D6B."""

from __future__ import annotations

from sentinel.polkit_noninteractive import (
    build_pkcheck_process_argv,
    classify_pkcheck_noninteractive,
    current_process_subject,
)


from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable

from sentinel.live_remediation_activation_lease import (
    TemporaryLiveRemediationActivationLease,
)
from sentinel.remediation_action_catalog import (
    RemediationActionEntry,
)
from sentinel.resource_bound_remediation import (
    BoundSystemdRemediationPlan,
)
from sentinel.runtime import (
    SentinelRuntime,
)


POLKIT_MANAGE_UNITS = (
    "org.freedesktop.systemd1.manage-units"
)


def _hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SystemdPrivilegePreflight:
    component_id: str
    target_fingerprint: str
    scope_fingerprint: str
    effect_fingerprint: str

    argv: tuple[str, ...]

    uid: int
    gid: int

    systemctl_binary: str
    polkit_action_id: str

    sudo_noninteractive: str
    polkit_noninteractive: str

    result: str

    def __post_init__(self) -> None:
        if self.result not in {
            "AUTHORIZED",
            "DENIED",
            "UNKNOWN",
        }:
            raise ValueError(
                "invalid privilege result"
            )

        valid_probe = {
            "AUTHORIZED",
            "DENIED",
            "UNAVAILABLE",
            "UNKNOWN",
        }

        if self.sudo_noninteractive not in valid_probe:
            raise ValueError(
                "invalid sudo result"
            )

        if self.polkit_noninteractive not in valid_probe:
            raise ValueError(
                "invalid polkit result"
            )

        if not self.argv:
            raise ValueError(
                "argv required"
            )

        if self.argv[0] != self.systemctl_binary:
            raise ValueError(
                "systemctl/argv mismatch"
            )

    @property
    def live_authorized(self) -> bool:
        return self.result == "AUTHORIZED"

    def canonical_dict(self) -> dict:
        return {
            "component_id":
                self.component_id,

            "target_fingerprint":
                self.target_fingerprint,

            "scope_fingerprint":
                self.scope_fingerprint,

            "effect_fingerprint":
                self.effect_fingerprint,

            "argv":
                list(self.argv),

            "uid":
                self.uid,

            "gid":
                self.gid,

            "systemctl_binary":
                self.systemctl_binary,

            "polkit_action_id":
                self.polkit_action_id,

            "sudo_noninteractive":
                self.sudo_noninteractive,

            "polkit_noninteractive":
                self.polkit_noninteractive,

            "result":
                self.result,
        }

    @property
    def fingerprint(self) -> str:
        return _hash(
            self.canonical_dict()
        )


def inspect_systemd_privilege(
    *,
    plan: BoundSystemdRemediationPlan,
    runner: Callable = subprocess.run,
    timeout: float = 3.0,
) -> SystemdPrivilegePreflight:
    if not isinstance(
        plan,
        BoundSystemdRemediationPlan,
    ):
        raise TypeError(
            "plan must be BoundSystemdRemediationPlan"
        )

    if timeout <= 0:
        raise ValueError(
            "timeout must be positive"
        )

    systemctl_binary = (
        plan.effect.argv[0]
    )

    if not Path(
        systemctl_binary
    ).is_absolute():
        raise ValueError(
            "systemctl path must be absolute"
        )

    if not os.path.isfile(
        systemctl_binary
    ):
        raise ValueError(
            "systemctl binary missing"
        )

    sudo_path = shutil.which(
        "sudo"
    )

    if sudo_path is None:
        sudo_result = "UNAVAILABLE"

    else:
        try:
            completed = runner(
                [
                    sudo_path,
                    "-n",
                    "true",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            sudo_result = (
                "AUTHORIZED"
                if completed.returncode == 0
                else "DENIED"
            )

        except (
            OSError,
            subprocess.TimeoutExpired,
        ):
            sudo_result = "UNKNOWN"

    pkcheck_path = shutil.which(
        "pkcheck"
    )

    if pkcheck_path is None:
        polkit_result = "UNAVAILABLE"

    else:
        try:
            completed = runner(
                list(
                    build_pkcheck_process_argv(
                        pkcheck_binary=pkcheck_path,
                        action_id=POLKIT_MANAGE_UNITS,
                        subject=current_process_subject(),
                    )
                ),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

            polkit_result = (
                classify_pkcheck_noninteractive(
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )

        except (
            OSError,
            subprocess.TimeoutExpired,
        ):
            polkit_result = "UNKNOWN"

    # Effect argv contains no sudo or pkexec.
    # Direct polkit/systemd authorization is therefore required.
    if polkit_result == "AUTHORIZED":
        final = "AUTHORIZED"

    elif polkit_result in {
        "DENIED",
        "UNAVAILABLE",
    }:
        final = "DENIED"

    else:
        final = "UNKNOWN"

    return SystemdPrivilegePreflight(
        component_id=(
            plan.effect.component_id
        ),

        target_fingerprint=(
            plan.effect.target_fingerprint
        ),

        scope_fingerprint=(
            plan.effect.scope_fingerprint
        ),

        effect_fingerprint=(
            plan.effect.fingerprint
        ),

        argv=tuple(
            plan.effect.argv
        ),

        uid=os.getuid(),
        gid=os.getgid(),

        systemctl_binary=(
            systemctl_binary
        ),

        polkit_action_id=(
            POLKIT_MANAGE_UNITS
        ),

        sudo_noninteractive=(
            sudo_result
        ),

        polkit_noninteractive=(
            polkit_result
        ),

        result=final,
    )


@dataclass(frozen=True, slots=True)
class SystemdControlledDryRunResult:
    privilege: SystemdPrivilegePreflight

    policy_decision: str
    policy_reason: str

    action_visible: bool
    bound_run_visible: bool
    catalog_visible: bool

    permit_claimed: bool
    execution_identity_claimed: bool
    effect_executed: bool

    state_restored: bool

    @property
    def hard_stopped(self) -> bool:
        return (
            not self.permit_claimed
            and not self.execution_identity_claimed
            and not self.effect_executed
        )


class SystemdControlledDryRun:
    def __init__(
        self,
        runtime: SentinelRuntime,
    ) -> None:
        if not isinstance(
            runtime,
            SentinelRuntime,
        ):
            raise TypeError(
                "runtime must be SentinelRuntime"
            )

        self.runtime = runtime

    def run(
        self,
        *,
        plan: BoundSystemdRemediationPlan,
        privilege: SystemdPrivilegePreflight,
        trigger: str | None = None,
    ) -> SystemdControlledDryRunResult:
        if not isinstance(
            plan,
            BoundSystemdRemediationPlan,
        ):
            raise TypeError(
                "plan must be BoundSystemdRemediationPlan"
            )

        if not isinstance(
            privilege,
            SystemdPrivilegePreflight,
        ):
            raise TypeError(
                "privilege must be SystemdPrivilegePreflight"
            )

        if (
            privilege.component_id
            != plan.effect.component_id

            or privilege.target_fingerprint
            != plan.effect.target_fingerprint

            or privilege.scope_fingerprint
            != plan.effect.scope_fingerprint

            or privilege.effect_fingerprint
            != plan.effect.fingerprint

            or privilege.argv
            != tuple(plan.effect.argv)
        ):
            raise PermissionError(
                "privilege_preflight_binding_mismatch"
            )

        runtime = self.runtime

        policy = runtime.policy

        catalog = (
            runtime.remediation_action_catalog
        )

        allowed_object = (
            policy.allowed_actions
        )

        allowed_snapshot = set(
            allowed_object
        )

        had_bound_attr = hasattr(
            policy,
            "_bound_effects_by_run",
        )

        bound_object = getattr(
            policy,
            "_bound_effects_by_run",
            None,
        )

        bound_snapshot = (
            None
            if bound_object is None
            else dict(bound_object)
        )

        entries_object = (
            catalog._entries
        )

        entries_snapshot = dict(
            entries_object
        )

        triggers_object = (
            catalog._trigger_map
        )

        triggers_snapshot = dict(
            triggers_object
        )

        entry = RemediationActionEntry(
            action=plan.effect.action,

            command=json.dumps(
                list(plan.effect.argv),
                separators=(",", ":"),
            ),

            rationale=(
                "D6B controlled dry-run metadata only; "
                "external execution prohibited."
            ),
        )

        lease = TemporaryLiveRemediationActivationLease(
            policy=runtime.policy,
            catalog=runtime.remediation_action_catalog,
            effect=plan.effect,
            entry=entry,
            trigger=trigger,
        )
        lease.activate()

        try:
            authorization = policy.evaluate_bound(
                incident_state="INVESTIGATING",
                effect=plan.effect,
            )

            if not authorization.authorized:
                raise RuntimeError(
                    "temporary activation did not authorize exact effect"
                )

            action_visible = (
                plan.effect.action
                in policy.allowed_actions
            )

            bound_visible = (
                plan.effect.policy_run_id
                in policy.list_bound_runs()
            )

            catalog_visible = (
                plan.effect.action
                in catalog.list_actions()
            )

            journal = (
                runtime.commander
                .remediation_orchestrator
                .identity_boundary
                .journal
            )

            if (
                journal.get_live_run_permit(
                    plan.effect.policy_run_id
                )
                is not None
            ):
                raise RuntimeError(
                    "D6B hard-stop violation: permit exists"
                )

            if (
                journal.get(
                    plan.effect.execution_id
                )
                is not None
            ):
                raise RuntimeError(
                    "D6B hard-stop violation: execution identity exists"
                )

            decision_value = authorization.decision
            decision_reason = authorization.reason
        finally:
            lease.close()

        state_restored = (
            policy.allowed_actions
            is allowed_object

            and set(
                policy.allowed_actions
            )
            == allowed_snapshot

            and catalog._entries
            is entries_object

            and dict(
                catalog._entries
            )
            == entries_snapshot

            and catalog._trigger_map
            is triggers_object

            and dict(
                catalog._trigger_map
            )
            == triggers_snapshot
        )

        if had_bound_attr:
            state_restored = (
                state_restored

                and getattr(
                    policy,
                    "_bound_effects_by_run",
                    None,
                )
                is bound_object

                and dict(
                    bound_object
                )
                == bound_snapshot
            )

        else:
            current = getattr(
                policy,
                "_bound_effects_by_run",
                None,
            )

            state_restored = (
                state_restored

                and (
                    current is None
                    or current == {}
                )
            )

        journal = (
            runtime.commander
            .remediation_orchestrator
            .identity_boundary
            .journal
        )

        permit = (
            journal.get_live_run_permit(
                plan.effect.policy_run_id
            )
        )

        execution = (
            journal.get(
                plan.effect.execution_id
            )
        )

        if permit is not None:
            raise RuntimeError(
                "D6B hard-stop violation: permit claimed"
            )

        if execution is not None:
            raise RuntimeError(
                "D6B hard-stop violation: execution identity claimed"
            )

        return SystemdControlledDryRunResult(
            privilege=privilege,

            policy_decision=decision_value,
            policy_reason=decision_reason,

            action_visible=action_visible,
            bound_run_visible=bound_visible,
            catalog_visible=catalog_visible,

            permit_claimed=False,
            execution_identity_claimed=False,
            effect_executed=False,

            state_restored=state_restored,
        )
