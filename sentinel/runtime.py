"""AIRIV Sentinel canonical runtime entrypoint."""

import sys
import time
import uuid

from sentinel.execution import ExecutionBoundary
from sentinel.commander import CommanderOrchestrator
from sentinel.commander_delivery import CommanderDeliveryProjector
from sentinel.commander_delivery_transport import CommanderDeliveryOrchestrator
from sentinel.incident_report_recorder import IncidentReportRecorder
from sentinel.incident_report_store import IncidentReportStore
from sentinel.incident_reporting import IncidentReportBuilder
from sentinel.incidents.manager import IncidentManager, Incident
from sentinel.remediation_evidence_flow import EvidenceCompleteRemediationFlow
from sentinel.remediation_gate import RemediationExecutionGate
from sentinel.remediation_orchestrator import RemediationOrchestrator
from sentinel.remediation_policy import RemediationPolicy
from sentinel.systemd_commander_integration import SystemdCommanderIntegration
from sentinel.systemd_production_preparation import (
    SystemdProductionPreparationBoundary,
)
from sentinel.systemd_production_execution_dispatch_gate import (
    SystemdProductionExecutionDispatchGate,
)
from sentinel.systemd_production_runtime_invocation import (
    SystemdProductionRuntimeInvocationBoundary,
)
from sentinel.systemd_production_runtime_delegation_bridge import (
    SystemdProductionRuntimeDelegationBridge,
)
from sentinel.systemd_production_activation_runtime_bridge import (
    SystemdProductionActivationRuntimeBridge,
)
from sentinel.tmux_remediation_verifier import (
    TmuxRemediationVerifier,
    TmuxVerificationTarget,
)
from sentinel.runtime_sensor_adapter import RuntimeSensorAdapter
from sentinel.unattended_reporting import UnattendedIncidentRollupBuilder
from sentinel.diagnostic.runtime_coordinator import (
    RuntimeDiagnosticCoordinator,
)


class SentinelRuntime:
    """Canonical runtime boundary for AIRIV Sentinel."""

    def __init__(self) -> None:
        self.last_canary_live_result = None
        self.last_production_probe_live_result = None
        self.last_gate3_live_result = None
        self.last_gate4_autonomous_result = None
        self.last_incident_report_sync_result = None
        self.last_incident_report_sync_error = None
        self.running = False

        self.execution = ExecutionBoundary()

        self.policy = RemediationPolicy()

        self.gate = RemediationExecutionGate(
            self.execution
        )

        self.orchestrator = RemediationOrchestrator(
            policy=self.policy,
            gate=self.gate,
        )

        # IncidentManager is the SOLE canonical incident authority.
        self.incident_manager = IncidentManager()

        # Reporting persistence is derived and non-authoritative. It receives
        # no Commander, policy, execution, or remediation capability.
        self.incident_report_store = IncidentReportStore()
        self.incident_report_recorder = IncidentReportRecorder(
            self.incident_report_store
        )
        self.incident_report_sync_interval_seconds = 60.0
        self._next_incident_report_sync_at = 0.0

        # External delivery is a separate, disabled-by-default effect boundary.
        # The default orchestrator owns only delivery identity plus a disabled
        # transport and is never called automatically by the daemon loop.
        self.commander_delivery = CommanderDeliveryOrchestrator()

        # Evidence flow records remediation evidence on the canonical Incident.
        self.remediation_flow = EvidenceCompleteRemediationFlow()

        self.commander = CommanderOrchestrator(
            incident_manager=self.incident_manager,
            execution=self.execution,
            remediation_policy=self.policy,
        )

        # Explicit capability only; production callers supply production_now to
        # execute_verified(). Its D8.4 guard opens durable state lazily per call.
        # Target/action/bound-effect configuration and incident dispatch remain
        # external to composition. Canary retains its separate integration.
        self.systemd_production_integration = SystemdCommanderIntegration(
            self.commander,
        )
        # D8.8B: inert pre-execution orchestration composition only.
        # No daemon path invokes prepare() automatically.
        self.systemd_production_preparation = (
            SystemdProductionPreparationBoundary()
        )
        # D8.9A: explicitly default-disabled pre-policy gate.
        self.systemd_production_execution_dispatch_gate = (
            SystemdProductionExecutionDispatchGate(
                enabled=False,
            )
        )
        # D8.9C: runtime-owned invocation facade; second fail-closed layer.
        self.systemd_production_runtime_invocation = (
            SystemdProductionRuntimeInvocationBoundary(
                gate=(
                    self.systemd_production_execution_dispatch_gate
                ),
                enabled=False,
            )
        )
        # D8.9D: third independent fail-closed runtime layer.
        # No delegation/integration object is stored here.
        self.systemd_production_runtime_delegation_bridge = (
            SystemdProductionRuntimeDelegationBridge(
                invocation=(
                    self.systemd_production_runtime_invocation
                ),
                enabled=False,
            )
        )
        # D8.10D: fourth independent fail-closed runtime layer.
        # It owns no activation grant or durable consumption store.
        self.systemd_production_activation_runtime_bridge = (
            SystemdProductionActivationRuntimeBridge(
                runtime_bridge=(
                    self.systemd_production_runtime_delegation_bridge
                ),
                enabled=False,
            )
        )

        # Canonical sensor pipeline:
        # TMUX Sensor -> Normalization -> State Machine -> Incident Bridge
        from sentinel.integration.bridge import SentinelIntegrationBridge

        self.sensor_adapter = RuntimeSensorAdapter(
            bridge=SentinelIntegrationBridge(
                incident_manager=self.incident_manager
            )
        )

        # Diagnostic Engine is connected only after canonical Incident
        # creation. IncidentManager remains the sole Incident authority.
        from sentinel.diagnostic.commander_handoff import CommanderHandoff
        from sentinel.remediation_action_catalog import RemediationActionCatalog

        self.remediation_action_catalog = RemediationActionCatalog()

        from sentinel.systemd_canary_live_execution import SystemdCanaryLiveExecution
        self.canary_live_execution = SystemdCanaryLiveExecution(
            self.commander, self.remediation_action_catalog,
        )

        from sentinel.systemd_production_probe_live_execution import (
            SystemdProductionProbeLiveExecution,
        )
        self.production_probe_live_execution = (
            SystemdProductionProbeLiveExecution(
                self.commander,
                self.remediation_action_catalog,
            )
        )

        # Gate 3 is a dormant one-shot inbox. With no exact request file,
        # cycle() performs no activation, policy evaluation, or execution.
        from sentinel.systemd_production_gate3_live_validation import (
            SystemdProductionGate3LiveValidation,
        )
        self.gate3_live_validation = (
            SystemdProductionGate3LiveValidation(self)
        )

        # Gate 4 is daemon-wired but default-disabled. Disabled cycle() returns
        # before even performing a read-only systemd observation. Host enablement
        # remains a separate Commander-approved milestone.
        from sentinel.systemd_production_gate4_autonomous_runtime import (
            SystemdProductionGate4AutonomousRuntime,
        )
        self.gate4_autonomous_remediation = (
            SystemdProductionGate4AutonomousRuntime(self)
        )

        self.diagnostic = RuntimeDiagnosticCoordinator(
            commander_handoff=CommanderHandoff(self.commander),
            incident_lookup=self.incident_manager.get_incident_by_id,
            remediation_action_catalog=self.remediation_action_catalog,
            incident_manager=self.incident_manager,
        )

    def invoke_systemd_production_remediation(
        self,
        *,
        activation_binding,
        authorization_context,
        incident_state: str,
        after_snapshot_provider,
        production_now: float,
        timeout: float = 5.0,
        production_attempts=(),
        active_production_effects: int = 0,
    ):
        """Explicit durable-authorization production runtime composition.

        The automatic daemon loop never calls this method. Stored runtime
        production layers remain disabled. The explicit composer validates
        canonical activation/authorization continuity and creates only
        per-call routing objects; no execution authority is stored here.
        """
        from sentinel.systemd_production_explicit_runtime import (
            invoke_explicit_systemd_production_runtime,
        )

        return invoke_explicit_systemd_production_runtime(
            activation_binding=activation_binding,
            authorization_context=authorization_context,
            integration=self.systemd_production_integration,
            incident_state=incident_state,
            after_snapshot_provider=after_snapshot_provider,
            production_now=production_now,
            timeout=timeout,
            production_attempts=production_attempts,
            active_production_effects=active_production_effects,
        )

    def get_incident_report(self, incident_id: str):
        """Return a read-only report from canonical active or terminal state.

        Reporting is intentionally non-authoritative. This method performs no
        policy evaluation, command execution, remediation, verification side
        effect, or incident lifecycle mutation.
        """
        return IncidentReportBuilder().build_from_manager(
            self.incident_manager,
            incident_id,
        )

    def sync_incident_reports(self):
        """Reconcile canonical Incident state into derived durable reports."""
        result = self.incident_report_recorder.sync(self.incident_manager)
        self.last_incident_report_sync_result = result
        self.last_incident_report_sync_error = None
        return result

    def _sync_incident_reports_if_due(self, monotonic_now: float | None = None):
        """Run bounded reporting reconciliation without risking core runtime.

        A reporting/storage failure remains fail-closed at the reporting
        boundary, is exposed through runtime state and stderr/journal, and does
        not disable monitoring or remediation. Retry is bounded by the same
        cadence instead of becoming a tight failure loop.
        """
        now = time.monotonic() if monotonic_now is None else monotonic_now
        if now < self._next_incident_report_sync_at:
            return None

        self._next_incident_report_sync_at = (
            now + self.incident_report_sync_interval_seconds
        )
        try:
            return self.sync_incident_reports()
        except Exception as exc:
            self.last_incident_report_sync_result = None
            self.last_incident_report_sync_error = (
                f"{type(exc).__name__}: {exc}"
            )
            print(
                "[SENTINEL][REPORTING] incident report sync failed: "
                f"{self.last_incident_report_sync_error}",
                file=sys.stderr,
                flush=True,
            )
            return None

    def get_unattended_rollup(
        self,
        *,
        window_start: str | None = None,
        window_end: str | None = None,
        generated_at: str | None = None,
    ):
        """Return a read-only unattended rollup from durable report state."""
        return UnattendedIncidentRollupBuilder().build_from_store(
            self.incident_report_store,
            window_start=window_start,
            window_end=window_end,
            generated_at=generated_at,
        )

    def get_commander_delivery_projection(
        self,
        *,
        window_start: str | None = None,
        window_end: str | None = None,
        generated_at: str | None = None,
    ):
        """Return an allowlisted brief for a future external transport."""
        rollup = self.get_unattended_rollup(
            window_start=window_start,
            window_end=window_end,
            generated_at=generated_at,
        )
        return CommanderDeliveryProjector().project(rollup)

    def deliver_commander_brief(
        self,
        *,
        delivery_id: str,
        destination_id: str,
        window_start: str | None = None,
        window_end: str | None = None,
        generated_at: str | None = None,
    ):
        """Explicitly invoke the separate Commander delivery boundary.

        The canonical runtime composes this boundary with a disabled transport.
        The daemon loop never calls this method automatically. A caller may
        replace the transport only through an explicit reviewed composition.
        """
        projection = self.get_commander_delivery_projection(
            window_start=window_start,
            window_end=window_end,
            generated_at=generated_at,
        )
        return self.commander_delivery.deliver(
            projection=projection,
            delivery_id=delivery_id,
            destination_id=destination_id,
        )

    def start(self) -> None:
        self.running = True
        self.diagnostic.start()
        print("[SENTINEL] Runtime started")

    def stop(self) -> None:
        self.running = False
        self.diagnostic.stop()
        print("[SENTINEL] Runtime stopped")

    def run_once(self):
        """Execute one canonical sensor/incident runtime cycle."""
        if not self.running:
            return []

        live_result = self.canary_live_execution.cycle()
        if live_result is not None:
            self.last_canary_live_result = live_result

        probe_live_result = (
            self.production_probe_live_execution.cycle()
        )
        if probe_live_result is not None:
            self.last_production_probe_live_result = probe_live_result

        gate3_result = self.gate3_live_validation.cycle()
        if gate3_result is not None:
            self.last_gate3_live_result = gate3_result

        gate4_result = self.gate4_autonomous_remediation.cycle()
        if gate4_result is not None:
            self.last_gate4_autonomous_result = gate4_result

        incidents = self.sensor_adapter.process_tick()
        self.diagnostic.submit(incidents)
        self._sync_incident_reports_if_due()
        return incidents

    def remediate(
        self,
        incident: Incident,
        action: str,
        command: str,
        execution_id: str | None = None,
    ):
        """Execute remediation exclusively through the canonical Commander."""

        if not isinstance(incident, Incident):
            raise TypeError(
                "incident must be a canonical Incident"
            )

        if execution_id is None:
            execution_id = str(uuid.uuid4())

        verifier = TmuxRemediationVerifier(
            TmuxVerificationTarget(
                pane_id=incident.component_id,
                expected_alive=True,
            )
        )

        result = self.commander.remediate(
            incident=incident,
            action=action,
            command=command,
            execution_id=execution_id,
            verifier=verifier.verify,
        )

        if result.remediation is None:
            raise RuntimeError(
                "Commander remediation completed without evidence"
            )

        return incident, result.remediation


def main() -> None:
    runtime = SentinelRuntime()
    runtime.start()

    try:
        while runtime.running:
            runtime.run_once()
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
