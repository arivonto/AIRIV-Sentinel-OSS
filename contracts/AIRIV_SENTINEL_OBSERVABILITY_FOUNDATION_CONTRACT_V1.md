# AIRIV Sentinel Observability Foundation Contract V1

Status: **LOCKED**

## Purpose

Define the first cross-cutting observability foundation for AIRIV Sentinel without creating a new authority-bearing subsystem.

This foundation is passive and read-only. It may project already-observed runtime facts into deterministic health and readiness views. It MUST NOT authorize remediation, execute effects, mutate Incident lifecycle, restart services, change deployment state, or become a policy source.

## Canonical boundaries

Observability consumes facts produced by existing canonical components. It does not replace or duplicate them.

- `HealthMonitor` remains the canonical in-process worker heartbeat/freshness reporter.
- `LiveEvidenceObservability` remains a runtime evidence projection surface.
- Incident lifecycle authority remains with `IncidentManager` under the existing locked pipeline.
- Remediation authorization remains exclusively with `RemediationPolicy`.
- Command effects remain exclusively behind the canonical execution boundary.
- Release planning remains non-authoritative and non-executable.

## Foundation outputs

The foundation MAY expose deterministic read-only projections for:

1. daemon/worker liveness and staleness;
2. worker health state counts;
3. incident/remediation outcome counts derived from existing evidence;
4. report reconciliation health;
5. Commander attention backlog visibility;
6. delivery identity/backlog visibility;
7. AI execution identity/verifier health;
8. release-preflight readiness visibility;
9. bounded resource-use measurements;
10. restart/upgrade continuity evidence.

SLO targets are not normative until the underlying measurements are demonstrated trustworthy and stable.

## Required semantics

### Observation only

Every exported value MUST be derived from existing facts or evidence. The observability layer MUST NOT infer semantic remediation permission or manufacture missing authoritative facts.

### Explicit freshness

Where time affects interpretation, projections MUST expose the observation timestamp and/or age used to derive freshness. Missing observations MUST remain distinguishable from stale or unhealthy observations.

### Determinism

For the same normalized input facts and query time, the projection MUST produce the same semantic result.

### Unknown and incomplete facts

Unknown, missing, malformed, or partially available evidence MUST be represented explicitly. It MUST NOT be silently converted into healthy, ready, succeeded, or authorized state.

### Failure isolation

Observability persistence or projection failure MUST NOT widen runtime authority and MUST NOT trigger remediation by itself. Existing runtime behavior may continue according to its governing contracts.

### Metadata minimization

Observability output MUST exclude credentials, secrets, raw provider prompts/results, unrestricted command content, and unnecessary host-private data. Existing disclosure boundaries continue to apply.

### Repository/CI safety

Tests and CI for this foundation MUST NOT restart production services, mutate external production state, perform live remediation, or require production credentials.

## Initial vertical slice

The first implementation slice is daemon/worker liveness and staleness projection using the existing `HealthMonitor` semantics.

The slice MUST preserve all four worker health states:

- `UNKNOWN`
- `HEALTHY`
- `UNHEALTHY`
- `STALE`

It MUST expose counts and per-worker read-only facts without adding polling, recovery, restart, policy, execution, or lifecycle mutation behavior.

## Acceptance gates

The foundation is not complete until:

- focused behavior tests pass;
- architecture tests prove no authority-bearing dependency is introduced;
- existing worker/daemon regressions pass;
- full regression passes;
- public distribution validation passes for public-eligible content;
- no hidden production effects are introduced.

## Non-goals / decision-gated work

This contract does not authorize:

- live AI provider activation;
- external Commander delivery;
- new production targets;
- rollback execution;
- generic shell or service-control authority;
- automatic remediation based solely on observability thresholds;
- production SLO enforcement.

Any such capability remains separately governed and Commander-reviewed.