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
- `IncidentManager.resolve()` as sole terminal lifecycle mutation boundary;
- durable evidence, execution identity, replay protection and terminal `UNKNOWN` semantics where side effects are possible;
- no blind retry of indeterminate effects;
- AI output as untrusted execution/intelligence output, never semantic authority;
- observability as passive projection, never policy or effect authority;
- release planning/validation remaining non-authoritative and non-executable;
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
-> public-distribution validation
-> canonical main
-> curated OSS parity
-> separately authorized host/live proof only when required
```

A capability is complete only when implementation, fail-closed tests, acceptance evidence and authority boundaries agree.

## Foundation Lock — COMPLETE

Autonomous Commander mission, frozen/change-controlled V1 architecture, centralized incident lifecycle, deny-by-default remediation policy, exact execution, independent verification, durable execution identity/replay semantics, 24/7 systemd runtime, Gate 3 controlled production proof, Gate 4 bounded autonomy, trusted-host/CI privilege separation and private-canonical/curated-public topology are established.

**Exit:** COMPLETE.

## Operational Evidence & Commander UX — CORE COMPLETE

Durable incident reports, atomic integrity envelopes, idempotent append-retentive reconciliation, bounded runtime reconciliation, unattended rollups, chronological Commander Attention Queue and disclosure-safe delivery projection are established.

**Exit:** CORE COMPLETE.

## Commander Delivery Transport Foundation — COMPLETE

Explicit transport protocol, disabled production default, durable delivery identity, projection/destination/transport bound-effect continuity, replay suppression, `SUCCEEDED / FAILED / UNKNOWN`, sanitized failure metadata and deterministic non-network proof are established. Daemon execution does not auto-send.

### External Commander Delivery Adapter — DECISION-GATED / DISABLED

Requires explicit channel/destination, credential/privacy boundaries, bounded timeout/retry behavior, provider acknowledgement semantics, duplicate suppression, controlled live proof and unattended-enable review.

## Verified AI Agent Operations — PROVIDER-NEUTRAL FOUNDATION CORE COMPLETE

Governing contract: `contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md` — **LOCKED**.

Established: canonical provider-neutral execution boundary, immutable request/result identity, default-disabled execution resource, independent verification, append-oriented evidence, durable `CLAIMED / RUNNING / SUCCEEDED / FAILED / UNKNOWN`, exact request SHA-256 continuity, replay suppression, metadata-only identity ledger and deterministic local no-network proof.

### Live AI Provider Adapter — DECISION-GATED / DISABLED

Provider/model selection, credentials, outbound network access, budgets, rate limits, disclosure policy and controlled live proof require explicit review. Provider output remains untrusted even after successful transport execution.

## Release / Upgrade / Rollback Planning & Verification — READ-ONLY CORE COMPLETE

Established:

- immutable `ReleaseArtifactManifest` with exact commit/tree/component identity;
- deterministic manifest fingerprint;
- `UpgradePreflight` with `READY / NOT_READY`;
- dirty/mismatched/non-fast-forward rejection;
- immutable `UpgradePlan` with no executor;
- rollback candidate permanently `UNAUTHORIZED` and non-executable in planning;
- exact artifact validation and immutable provenance;
- independent post-upgrade verification with `VERIFIED / FAILED / UNKNOWN`;
- no auto-rollback and no rollback authorization from verification.

### Upgrade / Rollback Execution — NOT AUTHORIZED

A future effect-capable slice requires a separate explicit contract, exact-effect continuity, durable attempt identity, pre/post state evidence, ambiguity handling and independent verification. No rollback effect is authorized by current planning or verification work.

## Observability, SLO & Recovery Hardening — PASSIVE FOUNDATION CORE ADVANCED

Governing contracts are LOCKED:

- `AIRIV_SENTINEL_OBSERVABILITY_FOUNDATION_CONTRACT_V1.md`;
- `AIRIV_SENTINEL_OBSERVABILITY_METRICS_RECONCILIATION_CONTRACT_V1.md`;
- `AIRIV_SENTINEL_OBSERVABILITY_ATTENTION_DELIVERY_AI_HEALTH_CONTRACT_V1.md`;
- `AIRIV_SENTINEL_OBSERVABILITY_RELEASE_UPGRADE_HEALTH_CONTRACT_V1.md`.

Completed passive slices:

- daemon/worker liveness and staleness with `UNKNOWN / HEALTHY / UNHEALTHY / STALE`;
- incident/remediation outcome projection;
- incident reconciliation health;
- Commander attention backlog visibility;
- delivery identity/backlog health;
- AI execution identity/verifier health;
- release-preflight readiness health;
- artifact-validation health;
- post-upgrade verification health;
- duplicate, missing and unknown fact visibility;
- observed rollback-authority anomaly reported as degradation, never as permission.

Validated state at this closeout:

- canonical focused Commander regression: **225 PASS**;
- canonical full regression: **2,252 PASS**;
- curated public focused Commander regression: **225 PASS**;
- curated public full regression: **2,236 PASS**;
- canonical-public delta: **16 tests**;
- canonical CI + Public Distribution: **PASS**;
- curated OSS source parity CI: **PASS**.

**Current boundary:** PASSIVE FOUNDATION CORE ADVANCED. Observability has no remediation, execution, deployment, rollback, provider or Incident-lifecycle authority.

### ACTIVE SAFE NEXT — Recovery Evidence & Failure Injection Foundation

Next work may establish deterministic, non-production recovery/failure-injection evidence for known failure classes without executing remediation. Required properties:

- synthetic/deterministic test inputs only at foundation stage;
- explicit injected-failure identity;
- before/after observation continuity;
- expected recovery-state classification;
- `UNKNOWN` for incomplete or ambiguous recovery evidence;
- no automatic restart/remediation/rollback;
- no production fault injection;
- no authority inferred from test outcomes.

### FOLLOWING SAFE SLICES

1. bounded resource-use measurements;
2. restart/upgrade continuity evidence hardening;
3. measurement trust/stability evaluation;
4. non-enforcing SLO definitions;
5. SLO enforcement only under a separate future authority decision.

## Bounded Production Target Expansion — PLANNED / COMMANDER-REVIEWED

Each additional autonomous production target requires exact identity, action allowlist, blast radius, cooldown, retry window, concurrency constraint, exact-effect continuity, independent post-effect verification and durable attempt evidence. No generic restart-anything or unrestricted shell authority is permitted.

## Canonical AIRIV Event+Job Integration — DEPENDENCY-GATDd

Sentinel may integrate only with the canonical AIRIV Event+Job Foundation and must not create a parallel Event Bus or Job Worker. Work begins only when the AIRIV platform adapter/interface is stable enough to consume without Sentinel inventing platform semantics.

## Fleet & Multi-host Control — LATER

Preconditions include stable host identity, cross-host execution identity, durable evidence correlation, explicit authority delegation, host-scoped policy/blast radius and recovery semantics for network partitions or uncertain remote effects. Remote shell access alone is not fleet control.

## Change control

Documentation clarification, test hardening and contract-preserving bug fixes proceed through normal engineering/CI gates. Contract amendments, architecture changes, new production effects, disclosure-boundary changes, live external delivery, provider credential activation, rollback execution and other high-risk capability expansion require explicit Commander-level review before activation.

## Definition of Done

A slice is DONE only when implementation matches governing contracts, success and fail-closed tests exist, security/docs/compile gates pass, focused regressions pass where relevant, full regression passes, curated-public validation passes for public-eligible content, hidden production effects are absent and evidence can reconstruct what happened and why.

## Immediate execution order

1. **Recovery Evidence & Failure Injection Foundation** — ACTIVE SAFE NEXT.
2. **Bounded Resource-use Measurements**.
3. **Restart/Upgrade Continuity Evidence Hardening**.
4. **Measurement Trust + Non-enforcing SLO Definition**.

Live AI providers, external Commander delivery, new production targets, production fault injection and rollback execution remain separately decision-gated.
