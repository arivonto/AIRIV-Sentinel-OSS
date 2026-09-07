# AIRIV Sentinel — AI Agent Execution Contract V1

**Status:** LOCKED  
**Authority:** AIRIV Sentinel Mission Contract V1  
**Scope:** AI agent execution boundary only

---

## 1. Purpose

This contract defines the canonical boundary for executing AI agents
within AIRIV Sentinel.

The AI agent is an execution resource.

The AI agent is NOT semantic authority, contract authority,
lifecycle authority, or remediation authority.

---

## 2. Authority Precedence

The following precedence is mandatory:

1. AIRIV Sentinel Mission Contract
2. AIRIV Sentinel contracts
3. Sentinel execution and policy boundaries
4. Verified runtime state
5. AI agent output
6. Local implementation preference

AI output MUST never override a higher authority.

---

## 3. AI Agent Role

An AI agent MAY:

- analyze supplied observations;
- classify or summarize supplied evidence;
- propose actions;
- generate commands or workflow steps as proposals;
- provide diagnostic reasoning;
- execute only through an explicitly authorized execution boundary.

An AI agent MUST NOT:

- modify Sentinel contracts;
- modify its own authority;
- directly change incident lifecycle state;
- directly mark an incident RESOLVED;
- bypass remediation policy;
- bypass execution gates;
- bypass verification;
- delete or rewrite evidence;
- grant itself additional permissions;
- treat its own output as proof of successful execution.

---

## 4. Canonical Execution Boundary

AI agent execution MUST pass through a canonical Sentinel boundary.

The minimum conceptual flow is:

    Agent Request
        |
        v
    Agent Execution Boundary
        |
        v
    AI Agent
        |
        v
    Raw Agent Result
        |
        v
    Sentinel Verification
        |
        v
    Evidence Trail

The AI agent MUST NOT directly mutate canonical Sentinel state.

---

## 5. Input Contract

Every AI agent execution request MUST have an explicit:

- request identifier;
- agent identifier;
- task identifier;
- input payload;
- requested operation;
- execution context;
- authority context.

Missing required execution identity MUST cause rejection.

---

## 6. Output Contract

AI execution MUST produce an observable result containing, at minimum:

- request identifier;
- agent identifier;
- task identifier;
- execution start timestamp;
- execution completion timestamp;
- output;
- execution status.

AI output MUST be treated as untrusted execution output until
validated by Sentinel.

---

## 7. Execution Authorization

AI agent execution MUST NOT imply authorization to perform system actions.

If an AI agent proposes a consequential action:

    AI Proposal
        -> Sentinel Policy
        -> Execution Gate
        -> System Execution
        -> Independent Verification

The AI agent MUST NOT bypass this sequence.

---

## 8. Remediation Boundary

AI agents MAY recommend remediation.

AI agents MUST NOT independently authorize consequential remediation.

Actual remediation authority remains with the canonical Sentinel
remediation policy and execution gate.

---

## 9. Contract Verification

AI-generated claims MUST NOT be accepted as contract verification.

Contract verification MUST use observable system state and the
canonical ContractVerifier or another explicitly authorized
verification boundary.

---

## 10. Incident Lifecycle

AI agents MUST NOT directly perform:

- OPEN -> INVESTIGATING;
- INVESTIGATING -> RESOLVED;
- any other canonical incident lifecycle mutation.

Incident lifecycle authority remains exclusively with IncidentManager.

---

## 11. Evidence

Every consequential AI execution MUST produce evidence sufficient
to establish:

- what agent executed;
- what request was executed;
- when execution occurred;
- what result was returned;
- whether Sentinel accepted or rejected the result.

Evidence MUST be append-oriented and MUST NOT be silently destroyed
or rewritten.

---

## 12. Failure Semantics

AI execution failure MUST remain observable.

A failed AI execution MUST NOT be represented as success.

If an AI-proposed remediation fails:

    failure
       -> evidence
       -> incident remains unresolved
       -> escalation according to Mission Contract

The AI agent MUST NOT conceal or reinterpret execution failure.

---

## 13. Verification

Successful AI execution does NOT equal successful system operation.

Where an AI agent performs or proposes consequential operations,
the resulting system state MUST be independently verified before
the operation may be considered successful.

AI self-report MUST NOT constitute independent verification.

---

## 14. Isolation

AI agents MUST be replaceable execution resources.

Sentinel MUST NOT depend on one specific AI provider or model for
its core authority model.

Gemini, OpenAI, Ollama, or another model/provider MAY serve as an
AI execution resource, but none becomes canonical authority merely
by being integrated.

---

## 15. Auditability

AI execution MUST be observable through the Sentinel evidence trail.

At minimum, the system MUST be able to establish:

    request
    -> agent
    -> execution
    -> result
    -> verification
    -> evidence

Claims without corresponding observable evidence MUST NOT be treated
as authoritative facts.

---

## 16. Security Boundary

AI-generated commands, code, or instructions MUST be treated as
untrusted input.

AI output MUST NOT automatically become unrestricted shell authority.

Any consequential system operation MUST pass through the canonical
execution and authorization boundaries.

---

## 17. Non-Goals

This contract does NOT define:

- a specific AI provider;
- a specific model;
- prompt engineering;
- model selection;
- AI memory;
- autonomous semantic authority;
- unrestricted AI shell access;
- workflow orchestration semantics.

Those concerns belong to separate contracts or implementation
boundaries.

---

## 18. Implementation Rule

Implementation MUST conform to this contract.

Implementation MUST NOT introduce a hidden AI execution path,
provider-specific authority path, lifecycle bypass, remediation
bypass, or evidence bypass.

---

## 19. Lock Rule

Once accepted as V1, this contract is LOCKED.

Changes require an explicit architectural revision.

---

**END OF CONTRACT**
