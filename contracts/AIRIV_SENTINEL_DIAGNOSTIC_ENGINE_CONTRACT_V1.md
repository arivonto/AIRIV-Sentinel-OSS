# AIRIV Sentinel — Diagnostic Engine Contract V1

## Status

LOCKED

This contract defines the autonomous diagnostic boundary of AIRIV Sentinel.

It does not replace, weaken, or modify any existing Sentinel V1 authority,
execution, verification, incident lifecycle, evidence, or systemd contracts.

---

## Mission

The Diagnostic Engine provides Sentinel with autonomous investigation
capability for an Incident.

Its purpose is to collect sufficient evidence to establish a defensible
diagnosis, or determine that diagnosis cannot be safely established.

Core principle:

> Sentinel may investigate autonomously, but diagnosis never creates
> execution authority.

---

## Investigation Identity

Every investigation MUST have a durable identity and state.

Minimum investigation context:

- investigation_id
- incident_id
- component_id
- trigger
- state
- diagnostic budget
- hypotheses
- observations
- diagnostic actions
- evidence
- diagnosis
- timestamps

Investigation state MUST survive Sentinel daemon restart.

---

## Diagnostic Action Identity

Every diagnostic attempt MUST have a durable:

`diagnostic_action_id`

Minimum action context:

- diagnostic_action_id
- investigation_id
- incident_id
- classification
- command
- state
- result
- evidence
- timestamps

Invariant:

> One diagnostic_action_id represents exactly one diagnostic attempt.

A repeated diagnostic attempt MUST receive a new diagnostic_action_id.

---

## Diagnostic Action Classification

### OBSERVE

Reads system state without changing system state.

Examples include:

- systemd state
- journal/log inspection
- process inspection
- tmux state
- network state
- filesystem state
- resource state
- application state
- other explicitly read-only observation

### DIAGNOSTIC

A diagnostic test explicitly classified as safe and intended to obtain
additional information.

### CONSEQUENTIAL

An operation capable of changing system state.

Examples include:

- restart
- kill
- modify
- delete
- install
- reconfigure

The Diagnostic Engine MUST NOT execute CONSEQUENTIAL operations directly.

Consequential operations MUST pass through the existing authority boundary:

Commander
→ Remediation Policy
→ Execution Identity
→ Execution
→ Verification
→ Evidence

### PROHIBITED

An operation forbidden by Sentinel policy.

The Diagnostic Engine MUST NOT execute PROHIBITED operations.

---

## Autonomous Investigation Loop

The canonical diagnostic loop is:

Incident
→ Investigation
→ Observation
→ Hypothesis
→ Diagnostic Action
→ Actual Result
→ Evidence
→ Hypothesis Evaluation
→ Next Action or Diagnosis

Hypotheses MAY be generated or updated with AI assistance.

AI output is untrusted.

AI hypotheses MUST NOT be treated as operational truth without supporting
actual system observations and evidence.

---

## Evidence Requirement

Every diagnostic action MUST produce an auditable record containing its
actual execution result and resulting observation/evidence.

Diagnosis MUST be based on evidence.

The Diagnostic Engine MUST distinguish:

- hypothesis
- observation
- result
- evidence
- diagnosis

The Diagnostic Engine MUST NOT represent an unverified hypothesis as fact.

---

## Diagnostic Budget

Every investigation MUST operate within explicit limits.

The diagnostic budget MUST support bounded investigation through:

- time budget
- action budget
- repetition budget
- risk boundary
- evidence requirement

Budget exhaustion MUST terminate autonomous investigation.

The Diagnostic Engine MUST NOT continue indefinitely.

The Diagnostic Engine MUST NOT reset or silently extend an exhausted budget.

---

## Investigation Terminal States

Canonical investigation terminal states:

- COMPLETED
- INSUFFICIENT_EVIDENCE
- BUDGET_EXHAUSTED
- ESCALATED

### COMPLETED

Sufficient evidence exists to establish a defensible diagnosis.

### INSUFFICIENT_EVIDENCE

Available evidence is insufficient to establish a defensible diagnosis.

### BUDGET_EXHAUSTED

Investigation stopped because an investigation budget boundary was reached.

### ESCALATED

The investigation requires Commander attention or another authorized
boundary.

---

## Durable Recovery

Diagnostic action state MUST be durable.

Canonical action states include:

- PLANNED
- RUNNING
- COMPLETED
- UNKNOWN

If Sentinel restarts before execution is established:

`PLANNED → recovery/reconciliation`

If Sentinel restarts while execution is in progress:

`RUNNING → UNKNOWN`

If the action result and evidence were durably committed:

`COMPLETED → reuse recorded result`

Invariant:

> UNKNOWN is not FAILED.

Invariant:

> UNKNOWN is not permission to retry.

The Diagnostic Engine MUST NOT blindly repeat an action whose execution
outcome is unknown.

If another diagnostic attempt is required, it MUST receive a new
diagnostic_action_id.

---

## Diagnosis and Authority Boundary

Diagnosis does not authorize remediation.

Canonical boundary:

Diagnosis
→ Commander
→ Authority / Policy
→ Remediation

The Diagnostic Engine MUST NOT infer execution authority from:

- diagnosis
- confidence
- urgency
- AI recommendation
- repeated failure
- absence of Commander response

Core principle:

> Knowledge does not create authority.

---

## Unattended Operation

Sentinel MUST be capable of autonomous investigation while Commander is
unavailable.

If autonomous remediation is authorized by the existing authority boundary,
Sentinel MAY proceed without Commander presence.

If Commander authorization is required, Sentinel MUST wait or escalate.

Sentinel MUST NOT bypass Commander approval merely because Commander is
asleep or unavailable.

---

## Operational Record

Every investigation MUST leave an operational record sufficient for the
Commander to reconstruct the event without repeating the investigation.

The record MUST support:

- Incident
- Detection
- Investigation
- Observations
- Hypotheses
- Diagnostic Actions
- Results
- Evidence
- Diagnosis
- Decision
- Remediation
- Verification
- Final State

This record is the operational history.

It MUST NOT replace the immutable Evidence Trail.

---

## Incident Lifecycle Boundary

Incident lifecycle authority remains exclusively with IncidentManager.

The Diagnostic Engine MUST NOT:

- create incidents outside IncidentManager
- resolve incidents directly
- bypass lifecycle rules
- redefine Incident semantics

The Diagnostic Engine operates within an existing Incident lifecycle.

---

## Existing V1 Boundary Preservation

This contract MUST NOT weaken or replace:

- IncidentManager
- Commander
- Remediation Policy
- Execution Identity
- Execution Gate
- Verification
- Evidence Trail
- systemd lifecycle
- existing Sentinel V1 contracts

The Diagnostic Engine adds autonomous investigation capability only.

---

## Safety Invariants

The Diagnostic Engine MUST:

- treat AI output as untrusted
- require evidence for diagnosis
- maintain bounded investigation
- preserve investigation history
- preserve diagnostic action identity
- survive daemon restart
- treat UNKNOWN as indeterminate
- prevent blind retry
- preserve evidence
- respect authorization boundaries
- escalate when safe autonomous continuation is impossible

The Diagnostic Engine MUST NOT:

- self-authorize consequential operations
- execute prohibited operations
- bypass Commander authority
- conceal failures
- fabricate evidence
- claim diagnosis without sufficient evidence
- retry indefinitely
- reset exhausted budgets
- silently alter contracts or architecture

---

## Canonical Autonomous Loop

The resulting Sentinel operational model is:

Detect
→ Incident
→ Investigate
→ Observe
→ Hypothesize
→ Test
→ Evidence
→ Diagnose
→ Decide
→ Authorize
→ Execute
→ Verify
→ Record
→ Recover

The Diagnostic Engine owns the investigation portion only.

Authority and execution remain governed by the existing Sentinel V1
architecture.

---

## Contract Principle

> Sentinel should investigate autonomously, reason with evidence, diagnose
> within bounded authority, and preserve enough operational history for the
> Commander to understand what happened even when the Commander was absent.

---

## Diagnostic Engine Facade Boundary

The `DiagnosticEngine` is the orchestration facade for autonomous
investigation.

The facade MUST coordinate the existing diagnostic authorities without
absorbing their responsibilities.

### Facade Responsibilities

The DiagnosticEngine MAY:

- orchestrate the investigation loop
- inspect investigation state
- request hypothesis evaluation
- request planning of the next diagnostic action
- request budget evaluation
- request diagnostic execution through DiagnosticExecutor
- request evidence recording through EvidenceAdapter
- request diagnosis evaluation through DiagnosisEvaluator
- request recovery reconciliation through RecoveryManager
- determine whether investigation continues or reaches a terminal state
- expose current investigation state

### Facade Authority Restrictions

The DiagnosticEngine MUST NOT:

- execute shell commands directly
- authorize consequential operations
- perform remediation
- create or resolve Incidents
- bypass IncidentManager
- directly write immutable Evidence Trail records
- reset or extend diagnostic budgets
- treat AI output as operational truth
- retry UNKNOWN diagnostic actions
- create diagnostic actions outside DiagnosticPlanner
- establish diagnosis independently of DiagnosisEvaluator

### Single-Step Execution Boundary

`DiagnosticEngine.step()` MUST process at most one diagnostic action attempt.

A single step MUST NOT internally execute an unbounded diagnostic loop.

The canonical step sequence is:

Investigation State
→ Current Hypotheses / Evidence
→ Diagnostic Planner
→ One Diagnostic Action
→ Budget Check
→ Budget Consumption
→ Diagnostic Executor
→ Evidence Adapter
→ Hypothesis Update / Evaluation
→ Diagnosis Evaluation
→ Terminal State or Next Step

Every diagnostic attempt MUST retain its own durable
`diagnostic_action_id`.

A subsequent diagnostic attempt MUST use a new
`diagnostic_action_id`.

### Terminal Boundary

The facade MUST stop autonomous investigation when:

- diagnosis is established
- evidence is insufficient
- diagnostic budget is exhausted
- autonomous continuation is unsafe or impossible

The facade MUST NOT silently continue after a terminal state.

### Recovery Boundary

`DiagnosticEngine.recover()` MUST delegate recovery to
`RecoveryManager`.

The facade MUST NOT retry UNKNOWN actions.

Recovery MUST reconcile durable state before autonomous investigation
continues.

### Existing Authority Preservation

The facade MUST preserve the authority boundaries of:

- IncidentManager
- Commander
- Remediation Policy
- Execution Identity
- Execution Gate
- Verification
- Evidence Trail
- DiagnosticExecutor
- BudgetManager
- InvestigationManager
- DiagnosticPlanner
- HypothesisManager
- DiagnosisEvaluator
- RecoveryManager

The DiagnosticEngine is an orchestration boundary only.

---
