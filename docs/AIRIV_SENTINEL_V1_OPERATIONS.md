# AIRIV Sentinel V1 — Operations

**Status:** FROZEN
**Operational State:** ACTIVE

## 1. Operational Objective

Sentinel provides continuous observation, controlled execution, independent verification, evidence collection, incident lifecycle management, and autonomous remediation within locked authority boundaries.

## 2. Runtime

Service: `airiv-sentinel.service`

Canonical entrypoint:
`/home/arivonto/airiv/airiv-sentinel/venv/bin/python -m sentinel.runtime`

## 3. Runtime Cycle

Observe → Normalize → Contract Verification → Incident Evaluation → State Classification

## 4. Remediation Rules

**DENY** — execution is rejected and identity is not consumed.

**ALLOW** — identity is claimed atomically, execution occurs once, verification follows, and evidence is finalized.

**REPLAY** — a consumed execution_id cannot execute again.

**UNKNOWN** — indeterminate execution outcome is terminal; automatic retry is prohibited.

## 5. Incident Operations

IncidentManager is the sole lifecycle authority.
Resolution requires explicit recovery evidence.

## 6. Evidence Operations

Execution, verification, AI-agent, and remediation evidence preserve consequential operational facts.

## 7. AI Operations

AI execution is provider-agnostic. AI output is untrusted until verification.

## 8. Failure and Recovery

Failed operations remain visible in evidence.
Interrupted CLAIMED or RUNNING execution identities recover as UNKNOWN.
Systemd provides daemon-level automatic recovery.

## 9. Operational Validation

Frozen V1 validation baseline:

- Full regression: 93 passed
- Canonical E2E / safety tests: 80 passed, 13 deselected
- Final operational proof: PASS
- Final gap review: PASS

## 10. Baseline

`baseline/AIRIV_SENTINEL_V1_BASELINE_FREEZE.md`

Baseline SHA-256:
`52675b8069b55c3ce95c4903ed08c3cce72bc3462a344c7b20cbddb7651dc7a1`

## 11. Release Boundary

Operational proof establishes V1 implementation integrity against its contracts. It does not by itself constitute commercial release approval.

## 12. Final State

**AIRIV Sentinel V1: OPERATIONALLY PROVEN AND FROZEN**
