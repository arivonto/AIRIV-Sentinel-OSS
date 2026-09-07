# AIRIV Sentinel — Commander Intent Contract V1

## 1. Purpose

This contract establishes the canonical semantic boundary for
**Commander Intent** within AIRIV Sentinel.

Commander Intent represents what the Autonomous Commander intends
to do after diagnosis and before authorization.

Commander Intent is a semantic decision layer.

It is NOT:
- DiagnosisStatus
- InvestigationState
- PolicyDecision
- authorization
- execution result
- verification result
- Incident final outcome

---

## 2. Canonical Decision Pipeline

The canonical Commander decision pipeline is:

    INCIDENT
        ↓
    DIAGNOSIS
        ↓
    COMMANDER INTENT
        ↓
    AUTHORIZATION
        ↓
    EXECUTION
        ↓
    VERIFICATION
        ↓
    INCIDENT FINAL OUTCOME

No layer may silently replace another layer.

---

## 3. Commander Intent Values

Commander Intent V1 consists of exactly four semantic intents:

### 3.1 NO_ACTION

The Commander determines that no remediation action should be
performed.

Properties:
- no remediation execution
- no authorization request for remediation
- no executable command
- incident remains subject to lifecycle/outcome determination

---

### 3.2 AUTONOMOUS_REMEDIATE

The Commander determines that Sentinel should attempt an
authorized autonomous remediation.

Properties:
- a remediation action may be selected
- authorization must occur before execution
- execution must occur through the canonical execution boundary
- execution success MUST NOT imply recovery
- independent verification is required before RECOVERED

Canonical path:

    AUTONOMOUS_REMEDIATE
        ↓
    AUTHORIZATION
        ↓
    EXECUTION
        ↓
    VERIFICATION
        ↓
    FINAL OUTCOME

---

### 3.3 NEED_COMMANDER

The Commander determines that autonomous execution must not
proceed and that human Commander intervention is required.

Properties:
- no autonomous remediation execution
- no executable command may be generated/executed as a consequence
- incident final outcome is normally ESCALATED unless a later
  Commander decision establishes another valid terminal outcome

---

### 3.4 INSUFFICIENT_EVIDENCE

The Commander determines that available evidence is insufficient
to safely establish an autonomous remediation intent.

Properties:
- no autonomous remediation execution
- no authorization for autonomous remediation
- no executable command
- incident final outcome is INSUFFICIENT_EVIDENCE unless a later
  valid lifecycle event establishes another outcome

---

## 4. Intent vs Authorization

Commander Intent and authorization are independent.

Example:

    Intent = AUTONOMOUS_REMEDIATE
    Authorization = DENY

This is valid.

The meaning is:

    The Commander intended autonomous remediation,
    but policy did not authorize execution.

The result MUST NOT be treated as successful remediation.

The canonical final outcome for this closed path is:

    ESCALATED

---

## 5. Intent vs Execution

Intent does not execute anything.

The following is prohibited:

    CommanderIntent → direct shell execution

The canonical boundary is:

    CommanderIntent
        ↓
    Authorization
        ↓
    ExecutionBoundary

No intent value itself may contain an executable command.

---

## 6. Intent vs Diagnosis

Diagnosis establishes the evidentiary state of an investigation.

Commander Intent determines the semantic course of action after
diagnosis.

Therefore:

    DiagnosisStatus ≠ CommanderIntent

In particular:

    DiagnosisStatus.ESTABLISHED
        does NOT automatically mean
    CommanderIntent.AUTONOMOUS_REMEDIATE

An established diagnosis permits a Commander decision; it does not
predefine the decision.

---

## 7. Intent vs Incident Final Outcome

Commander Intent is not the incident outcome.

For example:

    Intent = AUTONOMOUS_REMEDIATE
    Authorization = ALLOW
    Execution = SUCCESS
    Verification = SUCCESS
    Outcome = RECOVERED

Whereas:

    Intent = AUTONOMOUS_REMEDIATE
    Authorization = ALLOW
    Execution = FAILURE
    Outcome = UNRESOLVED

Therefore final outcome MUST be determined from the complete
incident lifecycle and evidence.

---

## 8. Canonical Outcome Mapping

The following closed-loop mappings are normative for V1:

### Scenario A — Successful autonomous recovery

    Intent       = AUTONOMOUS_REMEDIATE
    Authorization = ALLOW
    Execution    = SUCCESS
    Verification = VERIFIED
    Outcome      = RECOVERED

### Scenario B — Remediation execution failure

    Intent       = AUTONOMOUS_REMEDIATE
    Authorization = ALLOW
    Execution    = FAILURE
    Outcome      = UNRESOLVED

### Scenario C — Authorization denied

    Intent       = AUTONOMOUS_REMEDIATE
    Authorization = DENY
    Execution    = NONE
    Outcome      = ESCALATED

### Scenario D — Insufficient evidence

    Intent       = INSUFFICIENT_EVIDENCE
    Execution    = NONE
    Outcome      = INSUFFICIENT_EVIDENCE

### Scenario E — Commander intervention required

    Intent       = NEED_COMMANDER
    Execution    = NONE
    Outcome      = ESCALATED

---

## 9. Verification Rule

Execution success MUST NOT be interpreted as recovery.

Only independently verified post-remediation state may establish
the RECOVERED outcome for an autonomous remediation path.

Therefore:

    Execution SUCCESS
        +
    Verification absent
        ≠
    RECOVERED

And:

    Execution SUCCESS
        +
    Verification FAILED
        ≠
    RECOVERED

---

## 10. Incident Lifecycle Authority

Commander Intent does not own incident terminalization.

Remediation does not own incident terminalization.

Diagnosis does not own incident terminalization.

The canonical authority for incident lifecycle transition and final
outcome recording remains IncidentManager.

The final outcome MUST be recorded on the canonical Incident and
preserved in the evidence/history trail.

---

## 11. Evidence Requirements

Every autonomous Commander path must remain reconstructable.

Evidence must permit reconstruction of:

- incident identity
- diagnosis/investigation identity
- Commander Intent
- authorization decision
- authorization reason
- selected action
- execution identity
- execution result
- verification result
- final incident outcome
- relevant timestamps
- escalation or Commander intervention requirement where applicable

No semantic layer may erase evidence produced by a preceding layer.

---

## 12. Safety / Fail-Closed Rules

Commander Intent MUST fail closed.

The following are prohibited:

- implicit autonomous remediation without an explicit intent
- execution without authorization
- command embedded in Commander Intent
- treating policy ALLOW as proof of recovery
- treating execution SUCCESS as proof of recovery
- diagnosis directly terminalizing an incident
- remediation directly terminalizing an incident
- collapsing intent and authorization into one state
- collapsing diagnosis status and intent into one state
- collapsing final outcome into intent

---

## 13. Production Activation Boundary

Commander Intent implementation MUST NOT activate the production
remediation catalog.

Production remediation actions remain empty by default until the
complete autonomous loop has passed behavioral validation.

Test/dev actions may be used only inside isolated test boundaries.

---

## 14. Compatibility With Locked Boundaries

This contract does not authorize modification of:

- Execution Identity boundary
- Authorization boundary
- single-policy evaluation boundary
- Commander Handoff boundary
- Remediation Execution boundary
- existing IncidentManager authority

Implementation must integrate with those boundaries rather than
replace them.

---

## 15. Implementation Gate

Commander Intent implementation is permitted only after this
semantic contract is accepted.

The implementation gate requires:

1. canonical CommanderIntent type
2. canonical intent producer
3. Diagnosis → Intent boundary
4. Intent → Authorization boundary
5. intent-specific fail-closed paths
6. Incident final-outcome integration
7. evidence continuity
8. behavioral E2E validation
9. full regression validation

---

## 16. V1 Canonical Model

The canonical semantic model is:

    Diagnosis
        ↓
    CommanderIntent
        ↓
    Policy / Authorization
        ↓
    Execution Identity
        ↓
    Execution
        ↓
    Independent Verification
        ↓
    IncidentManager
        ↓
    Final Outcome

Commander Intent is a distinct architectural boundary.

END OF CONTRACT
