# AIRIV Sentinel Roadmap

> **Status:** ACTIVE / CHANGE-CONTROLLED
> **Roadmap baseline:** AIRIV Sentinel Project Lock — 2026-09-09
> **Canonical repository:** `AIRIV-Sentinel` — private canonical source
> **Public distribution:** `AIRIV-Sentinel-OSS` — curated open-source distribution

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
- `IncidentManager.resolve()` as sole terminal incident lifecycle mutation boundary;
- durable evidence, execution identity, replay protection and terminal `UNKNOWN` semantics where side effects are possible;
- no blind retry of indeterminate effects;
- AI output as untrusted execution/intelligence output, never semantic authority;
- Sentinel remaining external to AIRIV Server, Event Bus, Job Worker, API, database authority and business-domain authority;
- private canonical source + curated public distribution topology;
- production host effects separated from ordinary CI;
- reporting/delivery surfaces remaining non-authoritative;
- network delivery and live AI providers remaining disabled until explicitly reviewed.

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

A capability is complete only when implementation, fail-closed tests, acceptance evidence and authority boundaries agree.

---

## Foundation Lock — COMPLETE

Completed: Autonomous Commander mission, frozen/change-controlled V1 architecture, centralized incident lifecycle, deny-by-default remediation policy, exact execution, independent verification, durable execution identity/replay semantics, 24/7 systemd runtime, Gate 3 controlled production proof, Gate 4 bounded autonomy, trusted-host/CI privilege separation and private-canonical/curated-public topology.

**Exit:** COMPLETE.

---

## Operational Evidence & Commander UX — CORE COMPLETE

Completed slices include durable incident reports, atomic integrity envelopes, idempotent append-retentive reconciliation, bounded runtime reconciliation, unattended rollups, chronological Commander Attention Queue and exact-field disclosure-safe delivery projection.

**Exit:** CORE COMPLETE. Operational evidence can be summarized for Commander attention without becoming an authority-bearing subsystem.

---

## Commander Delivery Transport Foundation — COMPLETE

Completed slices include explicit transport protocol, disabled production default, durable delivery identity, projection/destination/transport bound-effect continuity, replay suppression, `SUCCEEDED / FAILED / UNKNOWN`, exception sanitization, metadata-only ledger and deterministic non-network local-file dry-run. Daemon execution does not auto-send.

**Exit:** COMPLETE. End-to-end delivery orchestration is proven without contacting an external recipient.

---

## External Commander Delivery Adapter — DECISION-GATED / DISABLED

Before email, webhook, chat or another network adapter can be enabled, explicitly define and review:

- exact channel and recipient/destination;
- credential source and rotation boundary;
- outbound-network boundary;
- timeout, retry/backoff and rate limits;
- provider acknowledgement and ambiguous-ack semantics;
- mapping of uncertainty to terminal `UNKNOWN`;
- privacy/disclosure policy;
- duplicate suppression;
- controlled live proof and independent verification;
- unattended-enable decision.

No default network transport is permitted.

---

## Verified AI Agent Operations — PROVIDER-NEUTRAL FOUNDATION CORE COMPLETE

Governing contract: `contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md` — **LOCKED**.

### Completed slices

- single canonical provider-neutral `AgentExecutionBoundary`;
- explicit immutable request/agent/task/operation/execution-context/authority-context identity;
- immutable raw result with terminal status validation;
- disabled adapter and deny-all verifier as fail-closed defaults;
- independent result-verification boundary;
- append-oriented AI execution evidence;
- sanitized provider/verifier exception handling;
- legacy AI executor consolidated as a compatibility facade to the canonical boundary;
- durable execution identity states `CLAIMED / RUNNING / SUCCEEDED / FAILED / UNKNOWN`;
- deterministic full-request SHA-256 binding and exact replay continuity;
- replay suppression, including incomplete attempt -> terminal `UNKNOWN` without automatic re-execution;
- metadata-only durable identity ledger excluding prompt/raw result/credential/system-command/Incident content;
- deterministic local no-network adapter, disabled by default;
- independent verifier that recomputes the expected local proof;
- tampered result rejection and ambiguous adapter failure -> `UNKNOWN` proof.

### Verified state

- canonical focused Commander regression: **225 PASS**;
- canonical full regression: **2,178 PASS**;
- curated public focused Commander regression: **225 PASS**;
- curated public full regression: **2,162 PASS**;
- canonical actual-main CI and Public Distribution: **PASS**;
- curated OSS AI sync CI: **PASS**;
- canonical-public delta remains **16 tests**, consistent with the curated private/public boundary.

### Foundation exit condition

A deterministic provider-neutral agent request executes through the canonical AI boundary, produces an observable raw result, receives independent acceptance/rejection, leaves reconstructable evidence, persists replay-safe execution identity and grants the AI no policy, lifecycle, contract, Commander, shell or remediation authority.

**Foundation exit:** CORE COMPLETE.

### Live AI Provider Adapter — DECISION-GATED / DISABLED

Provider selection and live activation are a separate capability decision. Before any OpenAI, Gemini, Ollama or other live adapter can be enabled, define and review:

- provider/model role and replaceability;
- credential source, rotation and disclosure boundary;
- outbound-network allow rules;
- time, cancellation, retry and resource/token budgets;
- rate limiting/backoff;
- ambiguous request/provider acknowledgement -> terminal uncertainty semantics;
- prompt/input/output disclosure policy;
- result verification based on observable Sentinel/system state where consequential;
- controlled live proof;
- explicit prohibition on direct shell, policy, lifecycle or remediation authority.

Provider output remains untrusted even after successful transport execution.

---

## Bounded Production Target Expansion — PLANNED / COMMANDER-REVIEWED

Each additional autonomous production target requires exact target identity, action allowlist, blast radius, cooldown, retry window, concurrency constraint, exact-effect continuity, independent post-effect verification and durable attempt evidence.

No generic restart-anything or unrestricted shell authority is permitted.

---

## Canonical AIRIV Event+Job Integration — DEPENDENCY-GATED

Sentinel may integrate only with the canonical AIRIV Event+Job Foundation and must not create a parallel Event Bus or Job Worker. Work begins only when the AIRIV platform adapter/interface is stable enough to consume without Sentinel inventing platform semantics.

---

## Packaging, Upgrade & Rollback — PLANNED

Future capability must include versioned artifacts, deterministic install validation, upgrade preflight, atomic/recoverable upgrade, post-upgrade verification, explicit rollback and release provenance without exposing private host state.

CI may coordinate evidence but must not gain general production/root authority.

---

## Fleet & Multi-host Control — LATER

Preconditions: stable host identity, cross-host execution identity, durable evidence correlation, explicit authority delegation, host-scoped policy/blast radius and recovery semantics for network partitions/uncertain remote effects.

Remote shell access alone is not fleet control.

---

## Observability, SLO & Recovery Hardening — CROSS-CUTTING

Ongoing scope includes daemon health, incident/remediation metrics, report reconciliation health, Commander attention backlog, delivery identities, AI execution identity/verifier health, failure injection, resource-use boundaries and restart/upgrade continuity.

---

## Change control

Documentation clarification, test hardening and contract-preserving bug fixes proceed through normal engineering/CI gates. Contract amendments, architecture changes, new production effects, disclosure-boundary changes, live external delivery, provider credential activation and other high-risk capability expansion require explicit Commander-level review before activation.

## Definition of Done

A slice is DONE only when implementation matches governing contracts, success and fail-closed tests exist, security/docs/compile gates pass, focused regressions pass where relevant, full regression passes, curated-public validation passes for public-eligible content, hidden production effects are absent and evidence can reconstruct what happened and why.

## Immediate execution order

Completed current safe slice: **provider-neutral Verified AI Agent Operations foundation**.

Decision-gated next capabilities are live AI-provider activation, external Commander delivery and production-target expansion. Safe non-live engineering may continue with packaging/upgrade/rollback and observability hardening without widening runtime authority.
