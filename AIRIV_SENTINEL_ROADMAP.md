# AIRIV Sentinel Roadmap

> **Status:** ACTIVE / CHANGE-CONTROLLED
> **Roadmap baseline:** AIRIV Sentinel Project Lock — 2026-09-09
> **Canonical repository:** `AIRIV-Sentinel` — Private / canonical source
> **Public distribution:** `AIRIV-Sentinel-OSS` — Public / curated open-source distribution

## Purpose

This roadmap sequences AIRIV Sentinel development without redefining its locked mission or authority model.

**Canonical precedence:** `Contract > Implementation > Roadmap > Local Preference`.

AIRIV Sentinel is the **Fail-closed Autonomous Commander** for the AIRIV development and runtime ecosystem. The human Commander retains final strategic authority.

## Non-negotiable invariants

Every roadmap slice MUST preserve:

- fail-closed/default-deny behavior;
- human Commander final strategic authority;
- `RemediationPolicy` as sole canonical remediation ALLOW/DENY authority;
- `ExecutionBoundary` as sole command-execution boundary;
- independent verification for consequential effects;
- `IncidentManager.resolve()` as sole terminal lifecycle mutation boundary;
- durable evidence, execution identity, replay protection, and terminal `UNKNOWN` semantics where side effects are possible;
- no blind retry of indeterminate effects;
- AI output as untrusted execution/intelligence output, never semantic authority;
- Sentinel remaining external to AIRIV Server, Event Bus, Job Worker, API, database authority, and business-domain authority;
- private canonical source + curated public distribution topology;
- production host effects separated from ordinary CI;
- reporting/delivery surfaces remaining non-authoritative;
- external delivery remaining disabled until transport-specific configuration and live proof are explicitly approved.

## Delivery model

```text
Locked requirement
-> engineering branch
-> focused tests
-> security / docs / compile gates
-> full regression
-> curated-distribution validation
-> canonical main
-> separately authorized host/live proof when required
-> curated OSS promotion
```

A feature is not complete merely because code exists. Completion requires acceptance evidence and preservation of authority boundaries.

---

## Foundation Lock — COMPLETE

Completed foundation:

- Autonomous Commander mission locked.
- V1 architecture frozen/change-controlled.
- centralized incident lifecycle and final-outcome separation;
- deny-by-default remediation policy;
- exact execution and independent verification;
- durable execution identity/replay/terminal uncertain-outcome semantics;
- 24/7 systemd runtime;
- Gate 3 controlled production proof PASSED / LOCKED;
- Gate 4 bounded production autonomy established;
- trusted-host/CI privilege separation;
- private canonical + curated public repository topology;
- synchronized project-lock documentation and disclosure validation.

**Exit:** COMPLETE.

---

## Operational Evidence & Commander UX — CORE COMPLETE

Completed vertical slices:

- read-only `IncidentReportBuilder` for active and terminal state;
- Commander-readable Markdown + immutable structured report;
- stable evidence timeline and classification;
- explicit Commander-attention derivation from canonical facts;
- malformed evidence rejection;
- runtime read-only report access;
- durable `IncidentReportStore` with atomic persistence and SHA-256 integrity envelope;
- strict identity/path validation and corrupt-state fail-closed behavior;
- idempotent `IncidentReportRecorder` reconciliation;
- append-retentive report persistence;
- immediate first runtime reconciliation and maximum one sync per 60 seconds afterward;
- nonfatal but visible reporting failures;
- `UnattendedIncidentRollup` and chronological `CommanderAttentionQueue`;
- timezone-aware start-inclusive/end-exclusive windows;
- exact-field `CommanderDeliveryProjection` disclosure allowlist;
- unreviewed schema drift rejected before transport projection.

Verified state at closeout:

- **225** focused production Commander-boundary tests PASS;
- **2,154** full canonical regression tests PASS;
- **2,138** full curated public regression tests PASS after public promotion;
- security/history, patch hygiene, docs/disclosure, compile, curated build and public-main CI PASS.

**Exit:** CORE COMPLETE. Durable unattended evidence can be summarized for Commander attention without becoming an authority-bearing subsystem.

---

## Commander Delivery Transport Foundation — COMPLETE

Completed vertical slices:

- explicit `CommanderDeliveryTransport` protocol;
- disabled/no-send production default;
- durable delivery identity ledger;
- projection digest + destination + transport bound-effect continuity;
- replay suppression;
- terminal `SUCCEEDED`, `FAILED`, and `UNKNOWN` semantics;
- no blind retry of terminal failure/uncertain outcome;
- exception sanitization: type recorded, raw exception message not persisted;
- delivery ledger excludes subject, body, raw incident evidence, and credentials;
- `CommanderDeliveryOrchestrator` consumes only `CommanderDeliveryProjection`;
- deterministic local file dry-run transport;
- dry-run artifact atomic/no-overwrite semantics;
- explicit `SentinelRuntime.deliver_commander_brief()`;
- daemon `run_once()` proven not to auto-send.

Verified state:

- canonical full regression: **2,154 PASS**;
- curated public full regression: **2,138 PASS**;
- focused production Commander-boundary regression: **225 PASS**;
- canonical main CI/Public Distribution PASS;
- curated OSS sync branch and actual public `main` CI PASS.

**Exit:** COMPLETE. A Commander brief can traverse the full delivery orchestration path using a non-network transport with durable identity, replay protection, fail-closed bound-effect continuity, and observable terminal semantics. No external recipient is contacted by this milestone.

---

## External Commander Delivery Adapter — DECISION-GATED

This is deliberately separate from the completed transport foundation.

Before email, webhook, chat, or another network adapter can be enabled, the following must be explicitly defined and reviewed:

- exact delivery channel;
- exact destination/recipient identity;
- credential source and rotation boundary;
- outbound network boundary;
- retry/backoff limits;
- provider acknowledgement semantics;
- mapping of timeout/ambiguous acknowledgement to terminal `UNKNOWN`;
- privacy/disclosure policy for projected content;
- rate limits and duplicate suppression;
- controlled live proof and independent verification;
- explicit unattended-enable decision.

No default network transport is permitted. Source deployment alone must never activate external delivery.

**Status:** DECISION-GATED / DISABLED.

---

## Verified AI Agent Operations — ACTIVE

Governing contract: `contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md` — LOCKED.

### Objective

Make AI-agent execution operationally useful while preserving Sentinel as the authority-bearing orchestrator and keeping providers replaceable.

### Active implementation sequence

1. Audit existing AI-agent execution modules/tests against the locked contract.
2. Define provider-neutral `AgentRequest` identity and validation boundary.
3. Define provider-neutral raw `AgentResult` and terminal execution states.
4. Add bounded time, retry, and resource budgets.
5. Add durable request/execution identity and replay semantics where consequential.
6. Add independent result-verification boundary; model self-report is never proof.
7. Record accepted/rejected result evidence without exposing credentials.
8. Prove the complete flow with a deterministic non-network fake/local adapter.
9. Only after the foundation is green, consider a provider-specific adapter through separate configuration/credential review.

### Mandatory acceptance criteria

- request identifier, agent identifier, task identifier, requested operation, execution context, and authority context are explicit;
- incomplete identity fails closed;
- AI output cannot directly mutate Incident lifecycle;
- AI output cannot authorize remediation or bypass policy/execution gates;
- failure, timeout, cancellation, and uncertain result are never reported as success;
- verifier is independent from AI output;
- consequential AI proposals still use canonical policy -> execution -> verification;
- evidence can reconstruct request -> agent -> execution -> result -> verification -> acceptance/rejection;
- no single AI provider becomes canonical authority;
- no live provider credential is required for the provider-neutral foundation.

### Exit condition

A deterministic provider-neutral agent request can execute through the canonical AI-agent boundary, produce a raw result, be independently accepted/rejected, and leave reconstructable evidence without granting the AI any policy, lifecycle, contract, or remediation authority.

---

## Bounded Production Target Expansion — PLANNED

Each additional autonomous production target requires its own explicit target identity, action allowlist, blast radius, cooldown, retry window, concurrency constraint, exact-effect continuity, independent post-effect verification, durable attempt evidence, and Commander-reviewed capability expansion where required.

No generic restart-anything or unrestricted shell authority is permitted.

---

## Canonical AIRIV Event+Job Integration — DEPENDENCY-GATED

Sentinel may integrate only with the canonical AIRIV Event+Job Foundation. It must not become or create a parallel Event Bus/Job Worker.

Required identity/correlation fields supplied by AIRIV must remain reconstructable, and at-least-once semantics require explicit idempotency behavior.

Work starts only when the relevant AIRIV platform adapter/interface is stable enough to consume without Sentinel inventing platform semantics.

---

## Packaging, Upgrade & Rollback — PLANNED

Required future capabilities:

- versioned release artifact;
- deterministic install validation;
- upgrade preflight;
- atomic/recoverable upgrade path;
- post-upgrade service verification;
- explicit rollback path;
- release provenance without public disclosure of private host state;
- curated OSS release flow separate from private canonical provenance.

CI may coordinate evidence but must not gain general production/root authority.

---

## Fleet & Multi-host Control — LATER

Preconditions include stable host identity, cross-host execution identity, durable evidence correlation, explicit authority delegation, host-scoped policy/blast radius, and recovery semantics for network partitions/uncertain remote effects.

Remote shell access alone is not fleet control.

---

## Observability, SLO & Recovery Hardening — CROSS-CUTTING

Ongoing scope:

- worker/daemon liveness and staleness;
- incident/remediation metrics;
- report-store/reconciliation health;
- Commander attention backlog visibility;
- delivery identity/backlog visibility;
- AI execution queue/budget/verifier health when introduced;
- failure injection and recovery tests;
- resource-use boundaries;
- upgrade/restart continuity;
- SLO definitions once measurements are trustworthy.

---

## Change control

Changes are classified as documentation clarification, test hardening, contract-preserving bug fix, contract amendment, architecture change, or capability expansion.

Contract amendments, architecture changes, new production effects, public/private disclosure changes, live external delivery, provider credential activation, and other irreversible/high-risk behavior require explicit Commander-level review before activation.

Routine implementation inside locked boundaries proceeds through normal engineering and CI gates.

## Definition of Done

A slice is DONE only when implementation matches governing contracts, success and fail-closed tests exist, security/docs/compile gates pass, focused regressions pass where relevant, full regression passes, curated-public validation passes for public-eligible content, hidden production effects are absent, required live proof is separately authorized, and evidence can reconstruct what happened and why.

## Immediate execution order

**ACTIVE NOW: Verified AI Agent Operations.**

The next slice is a provider-neutral request/result/execution boundary with deterministic non-network proof. Provider selection, credentials, and live-provider execution remain separate configuration and authorization decisions.
