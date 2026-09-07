"""Default-disabled Gate 4 autonomous production-probe daemon component.

When explicitly enabled by trusted host composition, this component observes
the single Gate 4 probe, creates a canonical Incident for an unhealthy state,
persists trusted pre-effect evidence, prepares one exact bound remediation,
and delegates through the bounded autonomous composer. It never creates or
accepts Commander approval evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import time
import uuid

from sentinel.incidents.manager import Incident
from sentinel.systemd_canary_live_observability import atomic_write, process_identity
from sentinel.systemd_evidence import (
    TrustedSystemdEvidenceRecord,
    TrustedSystemdEvidenceStore,
)
from sentinel.systemd_incident_dispatch import (
    SystemdDispatchEvidenceIdentity,
    SystemdIncidentDispatchAssessment,
)
from sentinel.systemd_production_bounded_autonomous import (
    ARGV,
    COMPONENT,
    UNIT,
    BoundedAutonomousSystemdCapability,
    invoke_bounded_autonomous_systemd_production,
)
from sentinel.systemd_production_gate4_enablement import load_gate4_capability
from sentinel.systemd_production_target_policy import ACTION_RESTART
from sentinel.systemd_remediation_safety import (
    SystemdPrivilegeBoundary,
    SystemdReadOnlyInspector,
    SystemdUnitSnapshot,
)


def default_root():
    return (
        Path.home()
        / ".local"
        / "state"
        / "airiv-sentinel-secure"
        / "gate4_bounded_autonomous"
    )


@dataclass(frozen=True, slots=True)
class Gate4AutonomousCycleResult:
    incident_id: str
    component_id: str
    execution_id: str | None
    final_outcome: str
    policy_authorized: bool | None
    execution_succeeded: bool | None
    verification_succeeded: bool | None
    error: str | None


class SystemdProductionGate4AutonomousRuntime:
    """Inert-by-default autonomous health-to-remediation daemon boundary."""

    def __init__(
        self,
        runtime,
        *,
        capability=None,
        root=None,
        clock=time.time,
        snapshot_provider=None,
    ):
        self.runtime = runtime
        self.capability = (
            load_gate4_capability()
            if capability is None
            else capability
        )
        if type(self.capability) is not BoundedAutonomousSystemdCapability:
            raise TypeError("BoundedAutonomousSystemdCapability required")
        self.root = Path(root) if root is not None else default_root()
        self.clock = clock
        self.snapshot_provider = (
            snapshot_provider
            if snapshot_provider is not None
            else lambda: SystemdReadOnlyInspector().inspect(UNIT)
        )
        if not callable(self.clock) or not callable(self.snapshot_provider):
            raise TypeError("clock and snapshot_provider must be callable")

    @staticmethod
    def _healthy(snapshot):
        return (
            snapshot.active_state == "active"
            and snapshot.sub_state == "running"
        )

    def _persist_result(self, result):
        payload = asdict(result)
        payload["schema"] = "airiv-sentinel-gate4-autonomous-cycle"
        payload["schema_version"] = 1
        payload["process"] = process_identity()
        atomic_write(
            self.root,
            "outcome-" + result.incident_id + ".json",
            payload,
        )

    def cycle(self):
        # Critical invariant: disabled means no observation, incident, policy,
        # evidence, execution, or systemd interaction of any kind.
        if not self.capability.enabled:
            return None

        before = self.snapshot_provider()
        if type(before) is not SystemdUnitSnapshot:
            raise TypeError("gate4_snapshot_provider_must_return_snapshot")
        if (
            before.identity.unit_name != UNIT
            or before.identity.component_id != COMPONENT
            or not before.identity.live_eligible
            or before.load_state != "loaded"
        ):
            raise ValueError("gate4_invalid_observation_target")

        if self._healthy(before):
            return None

        manager = self.runtime.incident_manager
        if manager.get_active_incident(COMPONENT) is not None:
            # Never take ownership of or execute through an existing incident.
            return None

        incident = None
        execution_id = None
        integration_result = None
        final_outcome = "UNRESOLVED"
        error = None

        try:
            incident = manager.evaluate_anomaly(
                observation={
                    "pane_id": COMPONENT,
                    "agent_identity": "AIRIV_SYSTEM",
                    "source": "GATE4_BOUNDED_AUTONOMOUS",
                },
                anomaly_type="SYSTEMD_PRODUCTION_PROBE_UNHEALTHY",
                reason="Gate 4 exact production probe is not active/running.",
            )
            manager.investigate(COMPONENT)

            now = float(self.clock())
            suffix = uuid.uuid4().hex[:16]
            execution_id = "gate4-execution-" + suffix

            evidence = TrustedSystemdEvidenceRecord(
                incident_id=incident.incident_id,
                component_id=COMPONENT,
                observation_id="gate4-observation-" + suffix,
                investigation_id="gate4-investigation-" + suffix,
                observed_at=now,
                snapshot=before,
            )
            store = TrustedSystemdEvidenceStore(self.root / "trusted_evidence")
            evidence_id = store.append(evidence)
            loaded = store.get(evidence_id)
            if loaded != evidence:
                raise ValueError("gate4_durable_evidence_roundtrip_failed")

            assessment = SystemdIncidentDispatchAssessment(
                candidate=True,
                incident_id=incident.incident_id,
                component_id=COMPONENT,
                unit=UNIT,
                action=ACTION_RESTART,
                reasons=("gate4_bounded_autonomous_candidate",),
                trusted_evidence_identities=(
                    SystemdDispatchEvidenceIdentity.from_record(loaded),
                ),
            )
            prepared = self.runtime.systemd_production_preparation.prepare(
                assessment=assessment,
                evidence=loaded,
                now=now,
                max_age_seconds=300.0,
                privilege=SystemdPrivilegeBoundary(systemctl_binary=ARGV[0]),
                run_id="gate4-run-" + suffix,
                execution_id=execution_id,
                permit_id="gate4-permit-" + suffix,
            )

            autonomous = invoke_bounded_autonomous_systemd_production(
                capability=self.capability,
                integration=self.runtime.systemd_production_integration,
                catalog=self.runtime.remediation_action_catalog,
                prepared=prepared,
                incident_state="INVESTIGATING",
                after_snapshot_provider=self.snapshot_provider,
                production_now=now,
                timeout=5.0,
            )
            delegated = autonomous.runtime_result
            integration_result = (
                delegated.integration_result
                if delegated is not None
                else None
            )

            if integration_result is not None and integration_result.recovered:
                final_outcome = "RECOVERED"

        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"

        if incident is not None:
            active = manager.get_active_incident(COMPONENT)
            if active is incident:
                manager.resolve(
                    component_id=COMPONENT,
                    recovery_evidence={
                        "source": "gate4_bounded_autonomous",
                        "execution_id": execution_id,
                        "policy_authorized": (
                            integration_result.authorization.authorized
                            if integration_result is not None
                            else None
                        ),
                        "execution_succeeded": (
                            integration_result.execution_succeeded
                            if integration_result is not None
                            else None
                        ),
                        "verification_succeeded": (
                            integration_result.verification_succeeded
                            if integration_result is not None
                            else None
                        ),
                        "error": error,
                    },
                    observation={
                        "pane_id": COMPONENT,
                        "agent_identity": "AIRIV_SYSTEM",
                    },
                    final_outcome=final_outcome,
                )

        result = Gate4AutonomousCycleResult(
            incident_id=incident.incident_id,
            component_id=COMPONENT,
            execution_id=execution_id,
            final_outcome=final_outcome,
            policy_authorized=(
                integration_result.authorization.authorized
                if integration_result is not None
                else None
            ),
            execution_succeeded=(
                integration_result.execution_succeeded
                if integration_result is not None
                else None
            ),
            verification_succeeded=(
                integration_result.verification_succeeded
                if integration_result is not None
                else None
            ),
            error=error,
        )
        self._persist_result(result)
        return result
