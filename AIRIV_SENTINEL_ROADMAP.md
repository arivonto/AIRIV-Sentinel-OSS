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
- `AIRIV_SENTINEL_OBSERVABILITY_RELEASE_UPGRADE_HEALTH_CONTRACT_V1.md`;
- `AIRIV_SENTINEL_OBSERVABILITY_RECOVERY_EVIDENCE_CONTRACT_V1.md`;
- `AIRIV_SENTINEL_BOUNDED_RESOURCE_MEASUREMENT_CONTRACT_V1.md`.
- `AIRIV_SENTINEL_SLO_ENFORCEMENT_DECISION_PACKAGE_V1.md`.

Completed passive/read-only slices:

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
- observed rollback-authority anomaly reported as degradation, never as permission;
- synthetic/non-production recovery evidence projection with explicit `RECOVERED / NOT_RECOVERED / UNKNOWN` semantics and no effect authority;
- bounded detached resource-measurement integrity projection with explicit units, bounded input and no host acquisition or SLO enforcement.
- detached measurement trust/stability evidence-quality projection with explicit source/window identity, duplicate detection and no host acquisition, thresholds, alerting, throttling or remediation.
- detached non-enforcing SLO definition projection with explicit metric/unit/window/scope identity and no sample evaluation, breach detection, alerting, throttling or remediation.
- non-executable SLO enforcement decision package with explicit Commander decision fields, mode vocabulary and required preconditions, without granting enforcement authority.

Historical validated state from the earlier observability closeout, before the later recovery-evidence and bounded-resource foundations were added:

- canonical focused Commander regression: **225 PASS**;
- canonical full regression: **2,252 PASS**;
- curated public focused Commander regression: **225 PASS**;
- curated public full regression: **2,236 PASS**;
- canonical-public delta: **16 tests**;
- canonical CI + Public Distribution: **PASS**;
- curated OSS source parity CI: **PASS**.

These historical counts are retained as closeout evidence only and MUST NOT be presented as current-suite counts after later merges.

**Current boundary:** PASSIVE FOUNDATION CORE ADVANCED. Observability has no remediation, execution, deployment, rollback, provider or Incident-lifecycle authority.

### Recovery Evidence Foundation — IMPLEMENTED / CONTRACT LOCKED

Canonical implementation and focused tests now exist for deterministic recovery evidence over caller-supplied synthetic/non-production facts. The projection preserves unknown/ambiguous evidence, rejects production-scoped or effect-attempting records as successful recovery proof, and does not inject faults, execute remediation, invoke verification or mutate Incident state.

This status does **not** authorize production fault injection or recovery execution.

### Bounded Resource Measurement Foundation — IMPLEMENTED / CONTRACT LOCKED

Canonical implementation and focused tests now exist for bounded, deterministic validation of caller-supplied resource samples. The foundation preserves fixed units, malformed/partial/unknown distinctions, duplicate identity and input truncation while remaining detached from host metric acquisition.

This status does **not** define SLO thresholds, poll production processes, alert, throttle or authorize remediation.

### Restart / Upgrade Continuity Evidence Hardening — IMPLEMENTED / INTEGRATED

PR #43 strengthens passive continuity evidence across restart and upgrade observations without creating a new execution, restart or rollback path. Integrated properties:

- exact observed artifact/runtime identity where available;
- explicit before/after continuity facts;
- preserved `UNKNOWN` when identity or continuity is incomplete;
- no inference that continuity evidence authorizes an effect;
- no automatic restart, deployment or rollback;
- deterministic/read-only tests only at foundation stage.

### Measurement Trust / Stability Evaluation — IMPLEMENTED / CONTRACT LOCKED

Implemented trust/stability evaluation projects detached measurement evidence quality without acquiring host metrics, defining enforcement thresholds, polling production processes, alerting, throttling, or authorizing remediation. Integrated properties:

- caller-supplied measurement facts only;
- explicit source identity and observation-window metadata where available;
- preserved `UNKNOWN` when source trust, units, timestamp, or continuity is incomplete;
- duplicate or contradictory samples reported as degradation;
- no SLO enforcement, alerting, throttling, restart, deployment, rollback, provider call, or lifecycle mutation;
- deterministic/read-only tests only at foundation stage.

### Non-Enforcing SLO Definitions — IMPLEMENTED / CONTRACT LOCKED

Implemented non-enforcing SLO definition projection defines descriptive SLO vocabulary and detached target records without evaluating live host state, comparing samples, detecting breaches, alerting, throttling, restart, deployment, rollback, provider calls, lifecycle mutation, or remediation authorization. SLO definitions remain descriptive planning evidence until a separate future authority decision explicitly permits enforcement.

Integrated properties:

- caller-supplied SLO definition facts only;
- explicit metric, objective relation/value/unit, observation-window and effective-scope identity;
- preserved `UNKNOWN` when required definition facts are missing;
- malformed or duplicate definition identities reported as degradation;
- no sample evaluation, breach status, alerting, throttling, restart, deployment, rollback, provider call, or lifecycle mutation;
- deterministic/read-only tests only at foundation stage.

### SLO Enforcement Decision Package — IMPLEMENTED / NON-EXECUTABLE

Implemented a non-executable decision package that defines the exact Commander decision record required before future SLO enforcement design may begin. It preserves the separation between descriptive SLO definitions, evidence-quality facts, reporting-only analysis, Commander-confirmed proposals and any future autonomous bounded enforcement.

Integrated properties:

- explicit decision identity, Commander authority identity, approved scope, SLO definition IDs, measurement source IDs and freshness window requirements;
- explicit mode vocabulary: `REPORT_ONLY`, `COMMANDER_CONFIRM`, `AUTONOMOUS_BOUNDED`;
- required blast-radius, cooldown, retry-budget, verification, rollback-position, production-activation and expiration facts;
- fail-closed handling for missing, ambiguous, contradictory, stale or non-durable decision facts;
- no live host metric acquisition, production breach detection, external alerting, throttling, restart, deployment, rollback, provider call, remediation authorization or Incident lifecycle mutation.

### ACTIVE SAFE NEXT — SLO Enforcement Authority Review

Commander decision recorded for a bounded passive scope: `sentinel-passive-observability-v1`,
`REPORT_ONLY`, with `report_projection` as the sole allowed consequence and no
specified SLO definitions or measurement sources. The decision enables only
the pure validation of this authority record; it does not authorize live
measurement acquisition or any consequential effect.

### SLO Report-Only Authority — IMPLEMENTED / NON-EXECUTABLE

The report-only authority contract and validator are integrated as a pure,
fail-closed boundary. Expiry, timestamp durability, mode, consequence, scope,
and identity completeness are validated locally. No runtime wiring or
production activation is implied.

### Bounded Pilot Host Evidence Projection — IMPLEMENTED / ACTIVATION PENDING

Implemented side-effect-free projection from caller-supplied host evidence into
the bounded pilot verification gate. The projection preserves exact service
identity, active/running state, PID presence, runtime identity continuity,
journal continuity, evidence-path validation and fail-closed reasons without
querying systemd, reading the journal, installing helpers, restarting Sentinel,
executing remediation or activating production.

### Commander Web / Desktop Surface Projection — IMPLEMENTED / READ-ONLY

The shared `sentinel/commander_surface.py` projection and [payload contract](contracts/AIRIV_SENTINEL_COMMANDER_SURFACE_PAYLOAD_CONTRACT_V1.md) are the first cross-surface
foundation for Sentinel Web and Sentinel Desktop. It accepts detached facts and
returns deterministic `READY`, `BLOCKED`, or `UNKNOWN` display state while
preserving exact service identity, evidence completeness, and
`PRODUCTION_EFFECT=NONE`. The projection also exposes the stable
`airiv.sentinel.commander_surface.v1` payload for independent surface clients.

The Web surface now exposes the boundary in the project dashboard. Desktop now
has a toolkit-neutral view model consuming the same projection contract, not a
second authority path. A native window toolkit remains a separate presentation
decision.
Neither surface may query systemd, read journals, execute commands, mutate
Incident lifecycle, authorize remediation, or activate production.

### FOLLOWING SAFE SLICES

1. SLO enforcement design remains separately gated and may begin only after a new explicit Commander authority decision selects non-reporting scope, mode and allowed consequences.

## Bounded Production Target Expansion — PLANNED / COMMANDER-REVIEWED

Each additional autonomous production target requires exact identity, action allowlist, blast radius, cooldown, retry window, concurrency constraint, exact-effect continuity, independent post-effect verification and durable attempt evidence. No generic restart-anything or unrestricted shell authority is permitted.

## Canonical AIRIV Event+Job Integration — DEPENDENCY-GATED

Sentinel may integrate only with the canonical AIRIV Event+Job Foundation and must not create a parallel Event Bus or Job Worker. Work begins only when the AIRIV platform adapter/interface is stable enough to consume without Sentinel inventing platform semantics.

## Fleet & Multi-host Control — LATER

Preconditions include stable host identity, cross-host execution identity, durable evidence correlation, explicit authority delegation, host-scoped policy/blast radius and recovery semantics for network partitions or uncertain remote effects. Remote shell access alone is not fleet control.

## Change control

Documentation clarification, test hardening and contract-preserving bug fixes proceed through normal engineering/CI gates. Contract amendments, architecture changes, new production effects, disclosure-boundary changes, live external delivery, provider credential activation, rollback execution and other high-risk capability expansion require explicit Commander-level review before activation.

## Definition of Done

A slice is DONE only when implementation matches governing contracts, success and fail-closed tests exist, security/docs/compile gates pass, focused regressions pass where relevant, full regression passes, curated-public validation passes for public-eligible content, hidden production effects are absent and evidence can reconstruct what happened and why.

## Immediate execution order

1. **SLO Enforcement Authority Review** — ACTIVE SAFE NEXT / Commander decision required.
2. **SLO Enforcement Design** — starts only after explicit Commander authority decision.

SLO enforcement, live AI providers, external Commander delivery, new production targets, production fault injection and rollback execution remain separately decision-gated.
