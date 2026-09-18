# AIRIV Sentinel Bounded Resource Measurement Contract V1

Status: **LOCKED**

## Purpose

Define bounded, deterministic, read-only projection of caller-supplied Sentinel resource measurements without acquiring host metrics, creating SLO thresholds, enforcing limits, or widening runtime authority.

The foundation validates detached measurements only. It does not poll processes, inspect `/proc`, invoke psutil, execute commands, restart workers, remediate incidents, or enforce an SLO.

It may additionally project caller-supplied measurement trust and stability facts. Trust/stability evaluation remains evidence quality classification only and MUST NOT become threshold enforcement, alerting, throttling, or remediation authority.

It may additionally project caller-supplied non-enforcing SLO definition records. These records are descriptive planning evidence only. They MUST NOT evaluate current measurements, poll production state, detect breaches, alert, throttle, authorize remediation, or mutate lifecycle state.

## Authority boundary

This foundation MUST NOT:

- read operating-system process state or host-private telemetry itself;
- use subprocess, shell, systemd, network clients, providers, or external monitoring services;
- authorize or execute remediation, restart, deployment, upgrade, rollback, or throttling;
- call `RemediationPolicy`, `ExecutionBoundary`, or Incident lifecycle mutation;
- define normative production SLO thresholds;
- convert measurement values into remediation permission;
- convert SLO definitions into breach, alert, throttle, restart, rollback, deployment, or remediation permission;
- auto-retry or auto-recover because of a measurement result.

Measurement integrity is diagnostic only.

## Detached sample schema

A sample may contain:

- `sample_id` — bounded stable symbolic identity;
- `observed_at_unix_seconds` — non-negative finite Unix timestamp in seconds;
- `cycle_duration_seconds` — non-negative finite runtime-cycle duration;
- `cpu_time_seconds` — non-negative finite accumulated CPU time;
- `rss_bytes` — non-negative integer resident-memory bytes;
- `open_fd_count` — non-negative integer open-descriptor count;
- `queue_depth` — non-negative integer queued-work count.

Fixed units are part of the projection surface. No unit inference is permitted.

## Detached trust/stability schema

A trust/stability record may contain:

- `sample_id` — bounded stable symbolic sample identity;
- `source_id` — bounded stable symbolic source identity;
- `observation_window_id` — bounded stable symbolic observation-window identity;
- `observed_at_unix_seconds` — non-negative finite Unix timestamp in seconds;
- `trust_status` — exactly `TRUSTED`, `UNTRUSTED`, or `UNKNOWN`;
- `stability_status` — exactly `STABLE`, `UNSTABLE`, or `UNKNOWN`.

The composite identity `(sample_id, source_id, observation_window_id)` is the detached trust/stability identity. Missing, malformed, duplicated, or contradictory identity facts are degradation and MUST NOT be silently normalized into trusted or stable evidence.

Trust/stability projection MUST preserve:

- explicit `UNTRUSTED`;
- explicit `UNSTABLE`;
- explicit `UNKNOWN`;
- missing or malformed identity/source/window/timestamp facts;
- duplicate composite identities.

`TRUSTED` and `STABLE` mean only that the caller-supplied evidence-quality facts were complete and internally consistent. They do not mean the measured resource values satisfy an SLO and do not grant authority to act.

## Detached non-enforcing SLO definition schema

A non-enforcing SLO definition record may contain:

- `slo_id` — bounded stable symbolic definition identity;
- `metric_name` — exactly one supported detached resource metric:
  - `cycle_duration_seconds`;
  - `cpu_time_seconds`;
  - `rss_bytes`;
  - `open_fd_count`;
  - `queue_depth`;
- `objective_relation` — exactly `TARGET_AT_OR_BELOW` or `TARGET_AT_OR_ABOVE`;
- `objective_value` — non-negative finite numeric objective value, integer-only for integer metrics;
- `objective_unit` — exact fixed unit matching the metric definition;
- `observation_window_id` — bounded stable symbolic observation-window identity;
- `effective_scope_id` — bounded stable symbolic descriptive scope identity.

The `slo_id` is the detached definition identity. Duplicate identities are degradation and MUST NOT be silently normalized into a single authoritative target.

SLO definition projection MUST preserve:

- missing required definition facts as `UNKNOWN`;
- malformed identity, metric, relation, objective, unit, window, or scope facts as `INVALID`;
- duplicate definition identities as `INVALID`;
- the descriptive objective relation and value without evaluating them against samples.

`COMPLETE` means only that the supplied definition record is structurally complete and internally consistent. It does not mean live resources satisfy the objective and does not grant authority to act.

## Sample classification

### `COMPLETE`

Stable sample identity and observation timestamp are present and valid, every defined resource metric is present and valid, and the sample identity is unique in the processed set.

### `PARTIAL`

Stable identity and timestamp are valid, at least one resource metric is valid, one or more resource metrics are absent, no provided metric is malformed, and identity is unique.

### `INVALID`

Any explicitly provided identity/timestamp/metric is malformed, negative, non-finite, boolean where numeric data is required, or the sample identity is duplicated.

### `UNKNOWN`

Required identity or observation timestamp is absent, or no valid resource measurement is available while no explicit malformed value establishes `INVALID`.

## Aggregate integrity

Aggregate `health` describes **measurement integrity only**, not resource sufficiency or production health:

- empty observation set: `UNKNOWN`;
- any `PARTIAL`, `INVALID`, `UNKNOWN`, duplicate identity, or input truncation: `DEGRADED`;
- otherwise: `HEALTHY`.

`HEALTHY` therefore means the supplied measurement set is structurally complete and internally consistent. It does not mean CPU, memory, file descriptors, queue depth, or cycle duration satisfy an SLO.

## Bounded processing

A single projection call processes at most **1,024 samples**. The projector may inspect one additional record only to determine overflow. Additional records are not materialized. Overflow MUST set `input_truncated=True` and aggregate integrity MUST be `DEGRADED`.

The processed count is explicit; the projector does not claim the total size of an unbounded input iterable.

## Required semantics

1. Read-only and side-effect free.
2. Deterministic for identical ordered inputs.
3. Immutable outputs.
4. Preserve processed sample order.
5. Preserve zero as a valid measurement.
6. Reject booleans as numeric measurements.
7. Reject negative or non-finite numeric measurements.
8. Duplicate sample identity is explicit and prevents complete/partial success for affected samples.
9. Missing and malformed facts remain distinguishable through sample status.
10. No normative thresholds, alerting rules, restart rules, remediation rules, or SLO enforcement.
11. No filesystem, `/proc`, psutil, subprocess, shell, systemd, network, provider, policy, execution, verifier, or Incident-lifecycle dependency.
12. CI/tests MUST NOT inspect or mutate external production state.
13. Measurement trust/stability projection remains detached from host acquisition and preserves incomplete, duplicate, untrusted, unstable, or unknown records as degradation.
14. Non-enforcing SLO definition projection remains detached from sample evaluation and preserves incomplete, malformed, duplicate, or unknown records as degradation.

## Acceptance gates

- complete/partial/invalid/unknown behavior tests;
- zero/negative/non-finite/boolean numeric tests;
- duplicate identity and bounded-input tests;
- deterministic/immutability tests;
- measurement trust/stability evidence-quality tests;
- non-enforcing SLO definition tests;
- architecture dependency-isolation test;
- full canonical regression;
- curated public distribution validation;
- no hidden host polling or production effects.

## Non-goals / separately decision-gated

This contract does not authorize:

- normative SLO targets;
- SLO enforcement;
- automatic alerting or remediation from thresholds;
- host/process metric acquisition;
- production fault injection;
- live provider activation;
- external Commander delivery;
- new production targets;
- upgrade or rollback execution.
