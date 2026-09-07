# AIRIV Sentinel — Production Systemd Preparation Contract V1

## Phase

2.13D.D8.8B

## Purpose

This boundary composes the already-locked production systemd
pre-execution pipeline into one explicit, inert preparation surface.

The canonical composition is:

D8.6 `SystemdIncidentDispatchAssessment`
→ D8.7A `TrustedSystemdEvidenceRecord`
→ D8.7A.1 `TrustedSystemdDispatchEvidenceBinding`
→ D8.7B canonical `BoundSystemdRemediationPlan`.

## Ownership

`SystemdProductionPreparationBoundary` owns orchestration of these
pre-execution transformations only.

It owns no semantic, authorization, execution, verification, durable
state, or incident lifecycle authority.

## Input

Preparation requires explicit caller-provided:

- canonical D8.6 dispatch assessment;
- canonical D8.7A trusted evidence record;
- handoff time;
- maximum evidence age;
- canonical `SystemdPrivilegeBoundary`;
- run ID;
- execution ID;
- permit ID.

It must not reconstruct target identity from strings or discover a
service independently.

## Evidence Binding

The preparation boundary must construct the canonical
`TrustedSystemdDispatchEvidenceBinding`.

Therefore assessment/evidence substitution and freshness semantics
remain owned by D8.7A.1.

The preparation boundary must not implement a second freshness rule.

## Plan Construction

The preparation boundary must invoke the canonical D8.7B
`build_bound_systemd_plan_from_trusted_binding()` function.

It must not implement a parallel bound-plan builder.

## Result

The result may contain:

- the canonical trusted dispatch/evidence binding;
- the canonical bound remediation plan;
- preparation time.

The result is pre-execution data only.

A prepared plan does not imply policy ALLOW.

## Explicit Non-Authorities

This boundary must not:

- evaluate `RemediationPolicy`;
- evaluate production target policy;
- call `SystemdCommanderIntegration.execute_verified`;
- call `production_runtime_guard`;
- claim an execution permit;
- create/update execution identity;
- write production attempts;
- acquire the production effect lease;
- execute a command;
- verify recovery;
- map final outcome;
- call `IncidentManager.resolve`;
- alter the incident lifecycle.

## Runtime Composition

`SentinelRuntime` may own one inert
`SystemdProductionPreparationBoundary`.

Construction of `SentinelRuntime` must not invoke `prepare()`.

`SentinelRuntime.run_once()` must not invoke `prepare()`.

No daemon or worker may automatically invoke production preparation in
D8.8B.

## Default State

Production target allowlist remains empty.

No production action or bound effect is automatically configured.

No filesystem state is created merely by constructing the preparation
boundary.

## Canary

The controlled-live canary path remains separate.

D8.8B must not route canary execution through this production
preparation surface.

## Future Execution

A later milestone may define an explicit dispatch/execution gate that
consumes a prepared plan and calls the already-existing canonical
production integration.

That future milestone must preserve the Commander and policy authority
boundaries and requires separate safety validation.
