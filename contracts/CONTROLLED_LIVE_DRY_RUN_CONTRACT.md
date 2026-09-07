# AIRIV Sentinel — Controlled-Live Dry-Run Contract

## Purpose

Validate the complete controlled-live remediation preparation path
without performing a live remediation effect.

## Canonical dry-run path

Isolated Workload Spec
→ Strong TMUX Sensor Observation
→ Incident
→ Investigation
→ Persistent Diagnostic Evidence
→ Bound TMUX Remediation Plan
→ Temporary Activation Lease
→ Commander Bound Authorization
→ HARD STOP

## Invariants

1. The workload is represented by an isolated run-scoped TMUX spec.
2. The dry-run must not activate/start the real TMUX workload.
3. Sensor evidence must carry strong TMUX identity.
4. Sensor evidence must match the isolated workload socket/session.
5. Sensor does not generate remediation `run_id`.
6. Incident `component_id` remains `pane_id`.
7. Strong identity is persisted through diagnostic evidence.
8. Bound plan is reconstructed from persisted evidence.
9. Remediation `run_id` is supplied externally.
10. Temporary policy/catalog activation is instance-local.
11. Commander evaluates the exact bound effect once.
12. Temporary activation is restored before dry-run returns.
13. `remediate_bound()` must never be called.
14. No execution permit may be claimed.
15. No command/effect may execute.
16. Production policy/catalog defaults remain empty after completion.
