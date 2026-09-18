# AIRIV Sentinel Commander Surface Payload Contract V1

**Status:** IMPLEMENTED / READ-ONLY
**Schema:** `airiv.sentinel.commander_surface.v1`
**Scope:** Sentinel Web and Sentinel Desktop display consumers

## Purpose

This contract defines the stable detached payload shared by Commander-facing
Web and Desktop surfaces. It projects already-observed facts into a bounded
display result. It is not a runtime API, command channel, policy source, or
production control surface.

## Authority boundary

The payload MUST remain read-only and MUST carry `production_effect: "NONE"`.
Consumers MUST NOT use it to authorize remediation, execute commands, mutate
Incident lifecycle, restart services, query systemd, read journals, or widen
production scope. Missing, unknown, or contradictory facts MUST remain
`BLOCKED` or `UNKNOWN`; they MUST NOT be promoted to `READY`.

## Top-level fields

| Field | Shape | Meaning |
| --- | --- | --- |
| `schema` | exact string | Payload schema identity and version. |
| `status` | `READY`, `BLOCKED`, `UNKNOWN` | Display classification only. |
| `reason` | bounded string | Deterministic display reason. |
| `headline` | bounded string | Human-readable display label. |
| `read_only` | exact boolean `true` | Confirms the surface boundary. |
| `production_effect` | exact string `NONE` | Explicit absence of production effect. |
| `facts` | object | Detached service, runtime, readiness, incident, and evidence facts. |

## Fact fields

`facts` contains `snapshot_id`, `observed_at`, `service_unit`,
`service_state`, `runtime_identity`, `readiness_state`, `active_incidents`,
`evidence_complete`, and `production_effect`. The implementation validates
exact service identity, bounded symbolic states, non-negative incident count,
boolean evidence completeness, and the `NONE` effect boundary before emitting
the payload.

## Non-goals

This contract does not define authentication, transport, persistence, host
acquisition, push delivery, native window management, or a live production
control plane. Those concerns require separate contracts and explicit review.
