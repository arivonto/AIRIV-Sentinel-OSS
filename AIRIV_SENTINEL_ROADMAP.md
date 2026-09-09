# AIRIV Sentinel Roadmap

> **Status:** ACTIVE / CHANGE-CONTROLLED
> **Roadmap baseline:** AIRIV Sentinel Project Lock — 2026-09-09
> **Canonical repository:** `AIRIV-Sentinel` — Private / canonical source
> **Public distribution:** `AIRIV-Sentinel-OSS` — Public / curated open-source distribution

## Purpose

This roadmap converts the locked AIRIV Sentinel concept, architecture, authority boundaries, verified production gates, and private/public distribution model into an implementation program.

The roadmap does **not** redefine the mission. It sequences capability work while preserving the canonical truth already established by contracts, frozen baseline records, implementation invariants, verified evidence, and the Project Lock documentation.

**Canonical precedence remains:**

`Contract > Implementation > Roadmap > Local Preference`

---

## Locked mission

AIRIV Sentinel is the **fail-closed Autonomous Commander** for the AIRIV development and runtime ecosystem.

The human Commander retains final strategic authority. Sentinel may observe, diagnose, orchestrate workflows and AI agents, execute system actions, verify contracts, manage incidents, preserve evidence, and perform autonomous remediation only inside explicit policy, authorization, safety, identity, replay, blast-radius, and independent-verification boundaries.

Capability never implies authority.

---

## Non-negotiable roadmap invariants

Every roadmap workstream MUST preserve all of the following:

- Human Commander remains final strategic authority.
- Production effects remain fail-closed and default-deny.
- `RemediationPolicy` remains the sole canonical ALLOW/DENY authority.
- `ExecutionBoundary` remains the sole command-execution boundary.
- `IncidentManager.resolve()` remains the sole terminal incident lifecycle mutation boundary.
- Verification remains independent; execution success alone is never recovery.
- Consequential actions and outcomes remain evidence-backed, observable, reconstructable, and auditable.
- AI output is an execution/intelligence resource, never semantic authority by itself.
- Execution identity, exact-effect continuity, replay protection, and terminal `UNKNOWN` semantics remain mandatory where side effects are possible.
- Indeterminate effects are never blindly retried.
- Autonomous production remediation remains bounded by explicit target/action/cooldown/retry/blast-radius/verification contracts.
- Sentinel remains external to AIRIV Server and does not replace AIRIV Server, API, database, Event Bus, Job Worker, or business-domain authority.
- Any AIRIV Event+Job integration uses the canonical AIRIV Event+Job Foundation; Sentinel must not create a parallel event/job authority.
- `AIRIV-Sentinel` remains the private canonical source.
- `AIRIV-Sentinel-OSS` remains a curated public distribution, not a mirror of private Git history or private operational provenance.
- Public publication remains explicit-allowlist, secret-scanned, disclosure-validated, and fail-closed.
- Production-host deployment or live remediation remains separately authorized from ordinary source-code CI.

---

## Execution model

Roadmap delivery uses one continuous engineering path:

`Locked requirement -> engineering branch -> focused tests -> security/docs/compile gates -> full regression -> curated-distribution validation -> canonical main -> separately authorized host/live proof when required -> curated OSS promotion`

A roadmap item is not considered complete merely because code exists. Completion requires its acceptance evidence and preservation of the canonical boundaries above.

---

## Foundation Lock — COMPLETE

### Objective

Establish a stable, auditable starting point from the agreed concept and all subsequent approved changes.

### Completed baseline

- Autonomous Commander mission locked.
- V1 architecture frozen and change-controlled.
- Incident lifecycle and final-outcome separation established.
- Evidence trail established as operational truth.
- Commander semantic and intent boundaries established.
- Default-deny remediation policy established.
- Exact execution and independent verification boundaries established.
- Execution identity, replay protection, and terminal uncertain-outcome semantics established.
- systemd 24/7 runtime established.
- Controlled production remediation Gate 3 passed and locked.
- Bounded autonomous production remediation Gate 4 established.
- Trusted-host / CI privilege separation established.
- Private canonical + curated public repository topology locked.
- `README.md` + `index.html` project-lock documentation synchronized and security-gated.
- Canonical and curated regression/security gates green at the roadmap baseline.

### Exit condition

**COMPLETE.** This baseline is the immutable conceptual input to subsequent roadmap work unless changed through explicit contract/change control.

---

## Operational Evidence & Commander UX — ACTIVE

### Objective

Turn Sentinel's existing incident/evidence machinery into an operational information surface that a Commander can trust during unattended and attended operation.

### Required capabilities

- Read-only incident report generation from canonical active and terminal incident state.
- Commander-readable Markdown representation.
- Structured JSON-compatible representation for later UI/API/notification adapters.
- Evidence timeline with stable ordering.
- Incident start/update time, anomaly identity, component/agent identity, lifecycle, final outcome, and evidence count.
- Detection and understanding summary.
- Diagnostic action summary.
- Remediation action summary.
- Independent verification result summary.
- Commander-required decisions/handoffs surfaced explicitly.
- Final status represented without inventing success.
- Fail-closed behavior for malformed evidence.
- Evidence indexing/retrieval without modifying Incident authority.
- Durable unattended incident summaries suitable for future delivery adapters.

### Active vertical slice

`IncidentReportBuilder` is the first implementation slice.

It MUST be:

- read-only;
- deterministic for a given incident snapshot;
- defensive against caller mutation;
- non-executing;
- non-authorizing;
- non-policy-making;
- non-lifecycle-mutating;
- usable for active and terminal incidents;
- capable of rendering Commander-ready Markdown and structured data.

### Acceptance criteria

- Active incident can be rendered without changing canonical Incident state.
- Terminal incident can be rendered from Incident history.
- Recovery/verification evidence is visible in the report.
- Escalated or explicit Commander-required evidence is visible as Commander attention.
- Malformed evidence is rejected rather than silently omitted.
- Report payload cannot be mutated through its read-only API.
- Returned serializable copies are defensive.
- Tests prove no command execution, no policy evaluation, and no lifecycle mutation is introduced by reporting.
- Full canonical regression and curated-distribution validation remain green.

### Follow-on slices

- Runtime read-only report access.
- Durable evidence index and incident lookup.
- Unattended session/overnight rollup.
- Commander attention queue derived only from canonical facts.
- Notification adapters after the report schema and evidence retention rules are stable.

---

## Bounded Production Target Expansion — PLANNED

### Objective

Expand autonomous remediation from the current deliberately narrow production profile without weakening safety.

### Rules

Each new target is treated as an independent capability expansion and requires:

- explicit target identity;
- explicit action allowlist;
- bounded blast radius;
- cooldown and retry-window policy;
- concurrency constraints;
- exact-effect fingerprint/continuity;
- independent post-effect verification;
- durable attempt/evidence continuity;
- fail-closed behavior for incomplete facts;
- explicit Commander approval for contract expansion where required.

No generic "restart anything" or unrestricted system command authority is permitted.

### Exit condition

At least one additional low-blast-radius target is proven through the same contract -> policy -> execution -> verification -> evidence discipline without creating general host authority.

---

## Verified AI Agent Operations — PLANNED

### Objective

Make AI-agent execution operationally useful while preserving Sentinel as the authority-bearing orchestrator.

### Required capabilities

- Provider-neutral execution adapter boundary.
- Explicit request identity and evidence continuity.
- Bounded time/retry/resource budgets.
- Result verifier independent from model output.
- Contract-aware acceptance/rejection of agent results.
- Failure/timeout/cancellation represented explicitly.
- No AI result may self-authorize remediation or change canonical contracts.
- Provider credentials remain outside public source and evidence payloads.

### Dependency

Operational Evidence & Commander UX must provide sufficient reporting and evidence continuity before AI-agent operations are expanded.

---

## Canonical AIRIV Event+Job Integration — DEPENDENCY-GATED

### Objective

Connect Sentinel to AIRIV asynchronous infrastructure without creating parallel authority.

### Required constraints

- Consume the canonical AIRIV Event+Job Foundation contract only.
- Preserve organization/actor/correlation/causation identity where supplied by AIRIV.
- At-least-once behavior must be paired with explicit idempotency semantics.
- Sentinel does not become AIRIV's Event Bus or Job Worker.
- Incident/evidence correlation must remain reconstructable across the integration boundary.

### Dependency

This workstream starts only when the relevant AIRIV Event+Job adapter/interface is stable enough to consume without Sentinel inventing missing platform semantics.

---

## Packaging, Upgrade & Rollback — PLANNED

### Objective

Make installation and controlled evolution repeatable while preserving fail-closed host boundaries.

### Required capabilities

- Versioned packaging/release artifact.
- Deterministic installation validation.
- Upgrade preflight.
- Atomic or recoverable upgrade path.
- Verified service restart/health validation.
- Explicit rollback path.
- Release provenance without exposing private host state.
- Curated OSS release flow separated from private canonical provenance.

### Rule

CI may coordinate release evidence but must not silently acquire general root/production authority.

---

## Fleet & Multi-host Control — LATER

### Objective

Extend Sentinel beyond a single-host trust model only after identity, evidence, and authority boundaries are strong enough to remain unambiguous across hosts.

### Preconditions

- Stable host identity contract.
- Stable execution identity across host boundaries.
- Durable evidence correlation.
- Explicit authority delegation model.
- Host-scoped policy and blast-radius enforcement.
- Recovery semantics for network partitions and uncertain remote effects.

No fleet control is introduced by merely adding remote shell access.

---

## Observability, SLO & Recovery Hardening — CROSS-CUTTING

### Objective

Continuously improve confidence that Sentinel itself is healthy, observable, recoverable, and diagnosable.

### Scope

- Worker/daemon health.
- Staleness and liveness signals.
- Incident and remediation metrics.
- Evidence-store health.
- Queue/backlog visibility where applicable.
- Restart/recovery behavior.
- Failure injection and recovery tests.
- Resource-use boundaries.
- Upgrade/restart continuity.
- Operational SLO definitions once measurements are trustworthy.

This workstream does not bypass feature-specific acceptance gates; it strengthens them.

---

## Roadmap change control

Changes are classified as:

- documentation clarification;
- test hardening;
- bug fix preserving contracts;
- contract amendment;
- architecture change;
- capability expansion.

Contract amendments, architecture changes, and capability expansions that change authority, production effects, public/private disclosure boundaries, or irreversible operational behavior require explicit Commander-level review/approval before those new powers become active.

Routine implementation details that remain inside already-approved boundaries may proceed through the standard engineering and CI gates.

---

## Definition of Done

A roadmap slice is **DONE** only when:

- implementation matches the governing contract/invariant;
- tests cover success and fail-closed paths;
- patch hygiene passes;
- security and credential/disclosure scans pass;
- affected documentation is valid;
- compilation passes;
- focused boundary regressions pass where relevant;
- full regression passes;
- public-distribution validation passes for public-eligible content;
- no hidden production effect is introduced by CI;
- any required live proof is separately authorized and independently verified;
- resulting evidence is sufficient to reconstruct what happened and why.

"No known failing automated gate" is a valid verified state. "Bug-free forever" or "unhackable" is not a valid engineering claim.

---

## Immediate execution order

**ACTIVE NOW:** Operational Evidence & Commander UX.

The first deliverable is the read-only unattended incident report boundary. After it is green on canonical and curated regression surfaces, development proceeds directly to runtime report access and durable evidence indexing before widening production autonomy or AI-agent authority surfaces.
