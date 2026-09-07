# AIRIV Sentinel — Workflow Execution Contract V1

**Status:** LOCKED  
**Authority:** AIRIV Sentinel Mission Contract V1  
**Scope:** Workflow execution boundary only

---

## 1. Purpose

This contract defines the canonical boundary for executing
multi-step workflows within AIRIV Sentinel.

A workflow is an ordered execution plan composed of explicit steps.

Workflow execution MUST remain observable, bounded, verifiable,
and subordinate to Sentinel authority.

---

## 2. Authority Precedence

The following precedence is mandatory:

1. AIRIV Sentinel Mission Contract
2. AIRIV Sentinel contracts
3. Workflow execution policy
4. Execution boundary
5. Verification boundary
6. Workflow definition
7. AI-generated workflow proposal

A workflow MUST NOT override a higher authority.

---

## 3. Workflow Definition

A workflow MUST have an explicit:

- workflow identifier;
- execution identifier;
- ordered steps;
- execution policy;
- verification requirements.

Each step MUST be independently identifiable.

Implicit or hidden execution steps are prohibited.

---

## 4. Canonical Execution Boundary

Workflow execution MUST pass through a canonical Sentinel boundary.

The conceptual flow is:

    Workflow Request
        |
        v
    Workflow Validation
        |
        v
    Step Authorization
        |
        v
    Execution Boundary
        |
        v
    Step Result
        |
        v
    Verification
        |
        v
    Evidence

A workflow MUST NOT directly bypass the canonical execution boundary.

---

## 5. Step Isolation

Each workflow step MUST produce an observable result.

A step MUST NOT silently depend on an unrecorded previous step.

Step dependencies MUST be explicit.

A failed step MUST NOT be silently treated as successful.

---

## 6. Execution Semantics

The canonical workflow lifecycle is:

    QUEUED
      |
      v
    RUNNING
      |
      +----> SUCCEEDED
      |
      +----> FAILED

A workflow MUST NOT enter SUCCEEDED unless all required steps
have completed successfully and required verification has passed.

---

## 7. Failure Semantics

When a required workflow step fails:

- the failure MUST be recorded;
- subsequent dependent steps MUST NOT execute;
- the workflow MUST NOT be declared successful;
- evidence MUST be preserved.

A workflow MAY support explicit failure-handling steps only when
those steps are part of the authorized workflow definition.

---

## 8. Authorization

Workflow execution MUST NOT itself grant system authority.

Every consequential step MUST remain subject to the applicable
Sentinel authorization and execution boundaries.

A workflow cannot bypass:

- remediation policy;
- execution gates;
- contract verification;
- incident lifecycle authority;
- evidence requirements.

---

## 9. Remediation Workflows

A workflow MAY contain remediation operations.

Such operations remain subordinate to the canonical remediation
policy and execution gate.

Workflow orchestration MUST NOT become an alternative remediation
authority.

---

## 10. AI-Generated Workflows

AI agents MAY propose workflows.

AI-generated workflow definitions MUST be treated as untrusted
input until validated.

AI-generated workflows MUST NOT:

- grant themselves authority;
- bypass workflow validation;
- bypass execution policy;
- bypass verification;
- mutate incident lifecycle directly;
- modify Sentinel contracts.

AI output is never semantic authority.

---

## 11. Incident Lifecycle

Workflow execution MUST NOT directly mutate canonical incident
lifecycle state.

Incident lifecycle authority remains exclusively with IncidentManager.

A workflow MAY produce evidence that supports an incident transition,
but the workflow itself MUST NOT perform that transition.

---

## 12. Verification

Workflow completion MUST be independently verifiable.

Successful execution of individual commands or steps does not,
by itself, prove successful workflow outcome.

Required postconditions MUST be checked by an authorized
verification boundary.

---

## 13. Evidence

Every workflow execution MUST produce evidence sufficient to
establish:

    workflow
      -> execution
      -> step
      -> result
      -> verification

Evidence MUST be append-oriented.

Evidence MUST NOT be silently destroyed or rewritten.

---

## 14. Idempotency

Workflow steps that may be retried MUST define retry semantics.

A retry MUST NOT silently create an unsafe duplicate operation.

Where idempotency cannot be guaranteed, the step MUST require
an explicit execution policy.

---

## 15. Retry and Recovery

Retries MUST be bounded and observable.

An implementation MUST NOT retry indefinitely.

Retry exhaustion MUST produce an observable workflow failure.

Recovery actions MUST remain subject to the same authorization
and verification boundaries as normal execution.

---

## 16. Concurrency

Concurrent workflow execution MUST NOT create an implicit authority
escalation.

Where two steps can conflict, their dependency or serialization
requirements MUST be explicit.

Shared system resources MUST remain subject to their applicable
execution boundaries.

---

## 17. Cancellation

A running workflow MAY be cancelled through an authorized
control path.

Cancellation MUST produce observable evidence.

Cancellation MUST NOT be represented as successful completion.

---

## 18. Timeout

Workflow execution and individual steps MAY have explicit timeouts.

Timeout MUST produce an observable failure condition.

A timed-out operation MUST NOT be assumed to have failed or succeeded
without appropriate verification.

---

## 19. Security Boundary

Workflow definitions MUST be treated as executable instructions.

Workflow content MUST NOT automatically become unrestricted
system authority.

Commands, scripts, or operations contained in a workflow MUST
pass through the applicable Sentinel execution and authorization
boundaries.

---

## 20. Auditability

Sentinel MUST be able to establish:

    workflow request
        -> validation
        -> authorization
        -> execution
        -> verification
        -> evidence

Claims about workflow completion MUST be supported by observable
evidence.

---

## 21. Non-Goals

This contract does NOT define:

- a specific workflow engine;
- a scheduler implementation;
- a specific queue technology;
- AI model selection;
- prompt engineering;
- business workflow semantics;
- a replacement for IncidentManager;
- a replacement for RemediationPolicy;
- unrestricted shell execution.

---

## 22. Implementation Rule

Implementation MUST conform to this contract.

Implementation MUST NOT introduce:

- hidden workflow steps;
- hidden retries;
- authorization bypasses;
- verification bypasses;
- lifecycle mutation outside IncidentManager;
- evidence destruction;
- implicit authority escalation.

---

## 23. Lock Rule

Once accepted as V1, this contract is LOCKED.

Changes require an explicit architectural revision.

---

**END OF CONTRACT**
