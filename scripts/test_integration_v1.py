import os
import sys
import yaml

sys.path.append(os.path.expanduser("~/airiv/airiv-sentinel"))

from sentinel.sensors.tmux.parser import TmuxStateParserV11
from sentinel.normalization.resolver import IdentityResolver, normalize_observations
from sentinel.state.state_machine import JobClassifier, StateMachine
from sentinel.incidents.manager import IncidentManager
from sentinel.integration.bridge import SentinelIntegrationBridge


NORMAL_STATES = {
    "IDLE",
    "OBSERVING",
    "TASK_ACTIVE",
    "WAITING",
    "COMPLETED",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    print("============================================================")
    print(" AIRIV SENTINEL — INTEGRATION CONTRACT V1 SEMANTIC GATE")
    print("============================================================")

    repo = os.path.expanduser("~/airiv/airiv-sentinel")
    config_path = os.path.join(repo, "config", "identities.yaml")

    require(
        os.path.exists(config_path),
        f"Configuration not found: {config_path}",
    )

    with open(config_path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    mapping_rules = {
        window: agent.upper()
        for agent, data in config.get("identities", {}).items()
        for window in data.get("windows", [])
    }

    parser = TmuxStateParserV11(
        target_session=config.get("session", "airiv")
    )
    resolver = IdentityResolver(mapping_rules=mapping_rules)

    raw = parser.inspect_panes()
    observations = normalize_observations(raw, resolver)

    require(observations, "[FAIL] No tmux observations discovered.")

    print(f"\n[INFO] Discovered {len(observations)} pane(s).")

    # ------------------------------------------------------------------
    # 1. NORMAL PATH
    # ------------------------------------------------------------------
    print("\n[TEST 1] Normal path")

    machines = {}

    for obs in observations:
        pane_id = obs["pane_id"]

        if pane_id not in machines:
            machines[pane_id] = StateMachine(component_id=pane_id)

        machine = machines[pane_id]

        job_type = JobClassifier.classify(obs)
        machine.set_job_type(job_type)
        state = machine.update_state(obs)

        incident_manager = IncidentManager()
        bridge = SentinelIntegrationBridge(
            incident_manager=incident_manager
        )

        incident = bridge.process_tick(obs, state)

        if state in NORMAL_STATES:
            require(
                incident is None,
                f"[FAIL] Normal state {state} created incident.",
            )
            require(
                not incident_manager.active_incidents,
                "[FAIL] Normal path created active incident.",
            )

    print("    [PASS] Normal states produce no incident.")

    # Use isolated manager/bridge for deterministic anomaly tests.
    test_obs = dict(observations[0])
    pane_id = test_obs["pane_id"]

    incident_manager = IncidentManager()
    bridge = SentinelIntegrationBridge(
        incident_manager=incident_manager
    )

    # ------------------------------------------------------------------
    # 2. STUCK
    # ------------------------------------------------------------------
    print("\n[TEST 2] STUCK anomaly")

    stuck = bridge.process_tick(test_obs, "STUCK")

    require(stuck is not None, "[FAIL] STUCK did not create incident.")
    require(stuck.status == "OPEN", "[FAIL] STUCK incident is not OPEN.")
    require(
        pane_id in incident_manager.active_incidents,
        "[FAIL] STUCK incident missing from active registry.",
    )

    incident_id = stuck.incident_id
    evidence_count = len(stuck.evidence_trail)

    print(f"    [PASS] STUCK opened {incident_id}.")

    # ------------------------------------------------------------------
    # 3. REPEATED ANOMALY
    # ------------------------------------------------------------------
    print("\n[TEST 3] Repeated anomaly")

    repeated = bridge.process_tick(test_obs, "STUCK")

    require(
        repeated is not None,
        "[FAIL] Repeated STUCK returned no incident.",
    )
    require(
        repeated.incident_id == incident_id,
        "[FAIL] Repeated anomaly created a different incident.",
    )
    require(
        len(repeated.evidence_trail) > evidence_count,
        "[FAIL] Repeated anomaly did not append evidence.",
    )
    require(
        len(incident_manager.active_incidents) == 1,
        "[FAIL] Repeated anomaly created multiple active incidents.",
    )

    print("    [PASS] Same incident preserved; evidence appended.")

    # ------------------------------------------------------------------
    # 4. NORMAL STATE MUST NOT AUTO-RESOLVE
    # ------------------------------------------------------------------
    print("\n[TEST 4] False recovery protection")

    normal = bridge.process_tick(test_obs, "TASK_ACTIVE")

    require(
        normal is None,
        "[FAIL] Normal transition returned an incident.",
    )
    require(
        pane_id in incident_manager.active_incidents,
        "[FAIL] Normal transition auto-resolved incident.",
    )
    require(
        incident_manager.active_incidents[pane_id].status == "OPEN",
        "[FAIL] Normal transition mutated incident lifecycle.",
    )

    print("    [PASS] Normal state did not auto-resolve.")

    # ------------------------------------------------------------------
    # 5. FAILED
    # ------------------------------------------------------------------
    print("\n[TEST 5] FAILED anomaly")

    failed_manager = IncidentManager()
    failed_bridge = SentinelIntegrationBridge(
        incident_manager=failed_manager
    )

    failed = failed_bridge.process_tick(test_obs, "FAILED")

    require(
        failed is not None,
        "[FAIL] FAILED did not create incident.",
    )
    require(
        failed.status == "OPEN",
        "[FAIL] FAILED incident is not OPEN.",
    )
    require(
        failed.component_id == pane_id,
        "[FAIL] FAILED component_id is not pane_id.",
    )

    print("    [PASS] FAILED opened incident.")

    # ------------------------------------------------------------------
    # 6. CONTRACT VIOLATION
    # ------------------------------------------------------------------
    print("\n[TEST 6] Contract violation")

    violation_manager = IncidentManager()
    violation_bridge = SentinelIntegrationBridge(
        incident_manager=violation_manager
    )

    violation = violation_bridge.process_contract_violation(
        observation=test_obs,
        violation_type="TEST_CONTRACT_VIOLATION",
        reason="Semantic gate contract violation test.",
        signal={
            "source": "integration_semantic_gate",
            "test": "contract_violation",
        },
    )

    require(
        violation is not None,
        "[FAIL] Contract violation did not create incident.",
    )
    require(
        violation.status == "OPEN",
        "[FAIL] Contract violation incident is not OPEN.",
    )
    require(
        violation.component_id == pane_id,
        "[FAIL] Contract violation component_id mismatch.",
    )
    require(
        len(violation.evidence_trail) >= 1,
        "[FAIL] Contract violation evidence was not preserved.",
    )

    evidence = violation.evidence_trail[-1]

    require(
        evidence["signal_type"] == "CONTRACT_VIOLATION",
        "[FAIL] Contract violation signal type not preserved.",
    )
    require(
        evidence["signal_snapshot"]["source"]
        == "integration_semantic_gate",
        "[FAIL] Contract violation signal evidence corrupted.",
    )

    print("    [PASS] Contract violation delegated and evidence preserved.")

    # ------------------------------------------------------------------
    # 7. EXPLICIT RECOVERY + EVIDENCE PRESERVATION
    # ------------------------------------------------------------------
    print("\n[TEST 7] Explicit recovery and evidence preservation")

    recovery_manager = IncidentManager()
    recovery_bridge = SentinelIntegrationBridge(
        incident_manager=recovery_manager
    )

    recovery_incident = recovery_bridge.process_tick(
        test_obs,
        "STUCK",
    )

    require(
        recovery_incident is not None,
        "[FAIL] Recovery test failed to create incident.",
    )

    original_id = recovery_incident.incident_id
    original_evidence_count = len(
        recovery_incident.evidence_trail
    )

    recovery_manager.resolve(
        component_id=pane_id,
        recovery_evidence={
            "status": "recovered",
            "method": "explicit_test_recovery",
        },
        observation=test_obs,
        operator_note="Integration V1 explicit recovery verification.",
    )

    require(
        pane_id not in recovery_manager.active_incidents,
        "[FAIL] Explicit recovery did not clear active incident.",
    )
    require(
        len(recovery_manager.incident_history) == 1,
        "[FAIL] Resolved incident not archived.",
    )

    archived = recovery_manager.incident_history[0]

    require(
        archived["incident_id"] == original_id,
        "[FAIL] Incident identity changed during recovery.",
    )
    require(
        archived["status"] == "RESOLVED",
        "[FAIL] Archived incident is not RESOLVED.",
    )
    require(
        len(archived["evidence_trail"]) > original_evidence_count,
        "[FAIL] Recovery evidence was not appended.",
    )

    recovery_entries = [
        entry
        for entry in archived["evidence_trail"]
        if entry["signal_type"] == "RECOVERY"
    ]

    require(
        recovery_entries,
        "[FAIL] RECOVERY evidence entry missing.",
    )

    print("    [PASS] Explicit recovery preserved lifecycle and evidence.")

    # ------------------------------------------------------------------
    # FINAL GATE
    # ------------------------------------------------------------------
    print("\n============================================================")
    print(" INTEGRATION CONTRACT V1 SEMANTIC GATE PASSED")
    print("============================================================")
    print("[PASS] Normal path")
    print("[PASS] STUCK")
    print("[PASS] FAILED")
    print("[PASS] Repeated anomaly")
    print("[PASS] False recovery protection")
    print("[PASS] Contract violation")
    print("[PASS] Evidence preservation")
    print("[PASS] Explicit recovery")
    print("============================================================")


if __name__ == "__main__":
    main()
