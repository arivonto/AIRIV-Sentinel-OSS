# AIRIV Sentinel V1 — Architecture

**Status:** FROZEN
**Target Capability:** Autonomous Commander

## 1. Architectural Principle

The canonical authority chain is:

```text
Observation
    ↓
Sensor / Runtime Adapter
    ↓
Contract Verification
    ↓
IncidentManager
    ↓
CommanderOrchestrator
    ↓
RemediationPolicy
    ↓
Execution Identity
    ↓
Execution Gate
    ↓
Execution
    ↓
Independent Verification
    ↓
Evidence
    ↓
Incident Lifecycle
```

## 2. Authority Precedence

```text
Contract > Implementation > Local Preference
```

## 3. Core Capabilities

- System monitoring
- System execution
- Workflow execution
- AI agent execution
- Contract verification
- Incident lifecycle management
- Evidence trail
- Remediation
- Independent verification
- Durable execution identity
- 24/7 daemon operation
- Terminal access
- Commander orchestration

## 4. Authority Boundaries

- IncidentManager is the sole incident lifecycle authority.
- CommanderOrchestrator is the orchestration boundary.
- RemediationPolicy controls authorization.
- Execution Identity controls remediation-attempt identity and replay protection.
- Execution Gate enforces authorized execution.
- Verification is independent from execution.
- Evidence preserves consequential operational facts.

## 5. AI Agent Boundary

AI output is untrusted until independently verified.
AI has no lifecycle, authorization, or evidence authority.

## 6. Remediation

Remediation is default-deny.
Authorized remediation follows policy → identity → gate → execution → verification → evidence.

## 7. Execution Identity

Every remediation attempt has a caller-supplied execution_id.
Identity is durable and replay-protected.

Supported states: CLAIMED, RUNNING, SUCCEEDED, FAILED, UNKNOWN.
UNKNOWN is terminal and must not trigger automatic retry.

## 8. Runtime

Service: airiv-sentinel.service

Canonical entrypoint:
`/home/arivonto/airiv/airiv-sentinel/venv/bin/python -m sentinel.runtime`

## 9. Locked Contracts

V1 is governed by nine locked Sentinel contracts covering mission, systemd, execution, remediation policy, verification, AI agents, workflows, Commander orchestration, and execution identity.

## 10. Baseline

Frozen baseline:
`baseline/AIRIV_SENTINEL_V1_BASELINE_FREEZE.md`

## 11. Change Control

Post-freeze changes must be explicitly classified as documentation-only, test-only, bug fix, contract amendment, architectural change, or capability expansion.

## 12. Final State

**AIRIV Sentinel V1 Architecture: FROZEN**
