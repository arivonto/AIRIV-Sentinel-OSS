# AIRIV Sentinel — Remediation Execution Identity Amendment V1

**Status:** APPROVED ARCHITECTURAL AMENDMENT  
**Applies to:** Remediation Execution / Commander Orchestration  
**Architecture Decision:** C — Contract-defined execution identity  
**Persistence Decision:** D — Durable filesystem-backed Execution Identity Journal

---

## 1. Purpose

This amendment establishes the canonical execution identity, duplicate/replay protection,
durable identity tracking, concurrency semantics, and interrupted-execution behavior for
AIRIV Sentinel remediation attempts.

This amendment supplements the existing Sentinel contracts.

Existing contracts remain authoritative except where this amendment explicitly adds
remediation execution identity semantics.

---

## 2. Canonical Execution Identity

Each remediation attempt MUST have exactly one canonical `execution_id`.

`execution_id` identifies ONE remediation execution attempt.

`execution_id` MUST:

- be supplied by the caller or orchestration boundary;
- be non-empty;
- remain stable for the lifetime of that remediation attempt;
- be propagated into execution outcome and remediation evidence.

`execution_id` MUST NOT be derived solely from:

- current timestamp;
- process ID;
- incident ID;
- action;
- command.

An `incident_id`, action, or command MUST NOT itself constitute a remediation
execution identity.

---

## 3. Identity Ownership

The Remediation Execution Identity Boundary owns:

- identity claim;
- duplicate detection;
- replay detection;
- durable identity state;
- atomic claim semantics;
- execution-state transitions;
- recovery of persisted execution state.

The Commander MUST NOT independently implement competing idempotency semantics.

The Commander MAY orchestrate the identity boundary but MUST NOT bypass it for
remediation execution.

---

## 4. Authorization Ordering

Authorization MUST occur before an execution identity is consumed.

Canonical ordering:

    remediation request
        -> authorization
        -> execution identity claim
        -> remediation execution
        -> outcome recording
        -> verification
        -> evidence finalization

A denied remediation MUST NOT consume an execution identity as an executed
remediation attempt.

---

## 5. Durable Execution Identity Journal

Execution identity state MUST be persisted in a durable filesystem-backed journal.

The journal MUST:

- survive Sentinel process restart;
- remain available across normal daemon restarts;
- provide atomic identity claim semantics;
- preserve execution state and outcome required for deterministic replay;
- NOT require a new database or event architecture.

The journal is an implementation boundary for execution identity.

It MUST NOT become:

- an incident lifecycle authority;
- a business database;
- an event bus;
- a replacement for the canonical Evidence Trail;
- a replacement for IncidentManager.

The exact filesystem location and serialization format are implementation details
and MUST NOT redefine the semantic contract.

---

## 6. Execution Identity State

The canonical V1 execution identity states are:

### `CLAIMED`

The execution identity has been atomically reserved.

No second request may claim the same identity.

### `RUNNING`

Execution has been initiated for the identity.

### `SUCCEEDED`

Execution completed with a successful execution result.

This state MUST NOT imply successful remediation verification.

### `FAILED`

Execution completed with a failed execution result.

### `UNKNOWN`

Execution outcome cannot be reliably determined.

This state MUST be used when Sentinel cannot establish whether the consequential
system operation completed, including interruption or process failure occurring
after execution may have started but before a reliable terminal outcome was
durably recorded.

`UNKNOWN` MUST be treated as consumed.

An `UNKNOWN` identity MUST NOT automatically execute again.

### `REPLAYED`

A request attempted to reuse an already-consumed execution identity.

`REPLAYED` represents the request outcome and MUST NOT cause another system
execution.

---

## 7. Canonical State Transition

Normal execution:

    CLAIMED
       |
       v
    RUNNING
       |
       +----> SUCCEEDED
       |
       +----> FAILED

Interrupted / indeterminate execution:

    CLAIMED or RUNNING
       |
       v
    UNKNOWN

Replay:

    consumed identity
       |
       v
    REPLAYED request

No transition may cause an already-consumed identity to execute a second time.

---

## 8. Atomic Claim

Claiming an unused execution identity MUST be atomic.

For concurrent requests using the same `execution_id`:

    Request A ----+
                  |
                  +----> Identity Boundary
                  |
    Request B ----+

exactly one request MAY obtain the execution claim.

The other request MUST be classified as duplicate/replay and MUST NOT execute
the remediation command.

The implementation MUST NOT use a non-atomic:

    check -> then create

sequence as its sole duplicate-protection mechanism.

---

## 9. Duplicate / Replay Semantics

When an already-consumed `execution_id` is submitted:

- the remediation command MUST NOT execute again;
- the request MUST receive a deterministic duplicate/replay result;
- previously persisted execution outcome MUST be returned when available;
- the request MUST remain observable through evidence;
- replay MUST NOT create a new remediation attempt.

A replay MUST NOT silently appear to the caller as a newly executed remediation.

---

## 10. Distinct Execution Identities

Different execution identities represent potentially distinct remediation attempts.

Therefore:

    execution_id=A
    execution_id=B

MAY both execute the same action against the same incident, provided each request
independently satisfies authorization and all other applicable boundaries.

Identity deduplication MUST NOT be based solely on:

- incident;
- component;
- action;
- command.

---

## 11. Denied Remediation

If authorization returns `DENY`:

- execution MUST NOT occur;
- the execution identity MUST NOT be consumed as an executed attempt;
- no execution claim may authorize execution;
- denial MUST remain observable through the canonical evidence flow.

A later authorized request MAY use a valid execution identity.

---

## 12. Execution Outcome

The execution outcome MUST remain distinct from remediation verification.

The following are separate facts:

    execution success
    verification success
    remediation success

Successful command execution MUST NOT automatically establish successful
remediation.

The canonical ExecutionBoundary remains responsible for system command execution.

---

## 13. UNKNOWN Outcome

`UNKNOWN` is a safety state.

If Sentinel cannot reliably determine whether the consequential operation occurred,
the corresponding execution identity MUST become `UNKNOWN`.

An `UNKNOWN` identity:

- MUST NOT be automatically retried;
- MUST NOT execute the same command again;
- MUST remain durably recorded;
- MUST remain observable through evidence;
- MAY require independent system-state investigation or verification;
- MAY require a new execution identity for any subsequently authorized attempt.

The system MUST NOT claim that the original execution succeeded merely because the
process was interrupted after execution began.

---

## 14. Evidence Requirements

`execution_id` MUST be included in remediation execution evidence.

At minimum, remediation evidence associated with an execution identity MUST preserve:

- execution_id;
- incident_id;
- component_id;
- action;
- authorization decision;
- authorization reason;
- execution outcome when known;
- verification outcome when available;
- duplicate/replay classification when applicable.

A duplicate/replay request MUST produce observable evidence.

Evidence remains append-oriented and the canonical Evidence Trail remains authoritative.

The execution identity journal MUST NOT replace the Evidence Trail.

---

## 15. Incident Lifecycle Boundary

This amendment does not change incident lifecycle authority.

`IncidentManager` remains the sole authority for canonical incident lifecycle state.

Execution identity state MUST NOT:

- resolve an incident;
- reopen an incident;
- change incident lifecycle authority;
- replace IncidentManager.

---

## 16. Verification Boundary

Verification remains independent from execution identity and execution result.

The verifier MUST independently observe the relevant post-remediation system state.

The following MUST remain distinct:

- execution identity;
- execution result;
- verification result;
- incident lifecycle state.

A replay MUST NOT be treated as a fresh execution merely because verification is
performed again.

---

## 17. Daemon Restart Semantics

Execution identity state MUST survive normal Sentinel daemon restart.

After restart:

- previously consumed identities MUST remain consumed;
- `SUCCEEDED` identities MUST NOT execute again;
- `FAILED` identities MUST NOT execute again;
- `UNKNOWN` identities MUST NOT execute again;
- replay behavior MUST remain deterministic.

An implementation relying exclusively on process memory is non-compliant.

---

## 18. Crash Safety

The implementation MUST account for crashes occurring between:

- identity claim;
- execution start;
- execution completion;
- durable outcome recording.

If execution may have occurred but reliable outcome recording did not complete,
the identity MUST resolve to `UNKNOWN` rather than being treated as unused.

Safety against duplicate consequential execution takes precedence over automatic
retry convenience.

---

## 19. Retry Semantics

A retry using the same `execution_id` is a replay, not a new remediation attempt.

A new remediation attempt MUST use a new execution identity.

The system MUST NOT silently transform:

    retry(execution_id=X)

into:

    execute(execution_id=Y)

without an explicit new remediation request and authorization.

---

## 20. Concurrency Guarantee

The implementation MUST guarantee that concurrent requests carrying the same
execution identity cannot both reach the canonical execution boundary.

This guarantee MUST hold across concurrent Sentinel execution contexts supported
by the implementation.

The guarantee MUST be based on the durable identity journal's atomic claim
mechanism, not merely on an in-process Python lock.

---

## 21. Authority Preservation

This amendment MUST NOT:

- redefine ExecutionBoundary;
- redefine RemediationExecutionGate;
- redefine RemediationPolicy;
- redefine Verification;
- redefine IncidentManager;
- introduce autonomous authority escalation;
- introduce a new database architecture;
- introduce an event bus;
- permit duplicate uncontrolled remediation.

Contract > Implementation > Local Preference remains authoritative.

---

## 22. Required V1 Validation

The implementation MUST prove:

1. Same `execution_id` executes at most once.
2. Repeated same `execution_id` does not execute.
3. Different `execution_id` MAY execute independently.
4. DENY does not consume the identity as an execution.
5. Execution outcome is durably attached to the identity.
6. `execution_id` appears in remediation evidence.
7. Duplicate/replay produces evidence.
8. Verification remains independent.
9. Identity survives daemon restart.
10. Concurrent same-identity requests cannot both execute.
11. Interrupted execution produces `UNKNOWN` when outcome is indeterminate.
12. `UNKNOWN` identity cannot automatically execute again.
13. Full Sentinel regression remains green.
14. Existing locked authority boundaries remain intact.

---

## 23. Implementation Boundary

This amendment authorizes implementation of:

    Remediation Execution Identity Boundary
        +
    Durable Filesystem-backed Execution Identity Journal
        +
    Atomic Claim
        +
    Duplicate / Replay Protection
        +
    UNKNOWN Outcome Handling

This amendment does NOT authorize unrelated architectural changes.

Production implementation MUST remain limited to the boundary defined here.

---

## 24. Final Contract Statement

For every Sentinel remediation:

    authorization
        -> identity claim
        -> execution
        -> durable outcome
        -> independent verification
        -> evidence

The same execution identity MUST NEVER cause more than one consequential
remediation execution.

When execution outcome is uncertain, Sentinel MUST prefer `UNKNOWN` over unsafe
duplicate execution.

This is the canonical V1 remediation execution identity model.
