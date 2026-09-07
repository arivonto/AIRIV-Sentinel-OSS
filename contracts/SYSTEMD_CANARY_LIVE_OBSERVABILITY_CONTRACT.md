# Systemd canary live observability V1

Phase 2.13D.D7D.2A.1. Repository implementation only.

## Ownership and paths

The systemd canary live surface publishes projections under its existing runtime
root: `AIRIV_SENTINEL_RUNTIME_DIR`, default repository `var/runtime`.
`systemd-canary-live-state.json` is current status;
`systemd-canary-live-evidence.json` is the latest processed request's evidence.
Neither file is ever read to request, authorize, permit, or replay work. Only
`systemd-canary-live-request.json` requests work. Existing permit and execution
identity journals remain authoritative; the evidence file is not a ledger.
RemediationPolicy remains the sole ALLOW/DENY owner. No new effects, services,
privileges, or control channels are introduced.

## Daemon cycle and state

`SentinelRuntime.run_once()` calls the surface's `cycle()` once. Empty cycles
publish IDLE without snapshots, policy evaluation, permit claims, or execution.
The lower-level absent-inbox `poll_once()` preserves its existing no-directory-
creation contract. Accepted requests publish PROCESSING before activation and
again with activation installed. The single canonical `execute_verified` result
is retained by object identity as `last_result` and `last_canary_live_result`;
subsequent empty cycles do not erase it. Runtime's incidents return is unchanged.

State schema version 1 includes Linux boot ID, PID, kernel process start ticks,
monotonically increasing surface write generation, timestamp, phase, pending
inbox existence, active request/approval IDs, last terminal request/outcome, and
separate policy/catalog/bound activation emptiness facts. Catalog triggers count
as activation. Aggregate emptiness additionally requires no cleanup uncertainty
or failed evidence persistence. Unknown configuration fails closed.

Terminal states are TERMINAL_SUCCESS or TERMINAL_FAILURE. These describe only
this live request's canonical `recovered` result plus cleanup/persistence, not
incident lifecycle outcomes. They never mutate incidents. After terminal
publication the next empty daemon cycle publishes IDLE retaining last terminal
IDs. Cleanup exceptions latch aggregate emptiness false even if individual
surfaces happen to look empty. No nonempty preexisting configuration is cleared.

## External pre-request proof

`valid_idle_projection` is read-only evidence validation. Supply independently
observed current daemon identity (not identity trusted from the projection),
current time and a bounded freshness allowance (default five seconds). It
cross-checks the Linux process identity, schema, positive write generation,
fresh timestamp, IDLE, no pending inbox, null active IDs, and all emptiness
booleans. Malformed, old-boot, reused-PID, previous-process, future or expired
records fail. A file is a sampled fact, not a lock or authorization: external
pre-gates must also independently check the running daemon and canonical inbox
and retain their other requirements. Process identity is boot/PID/start-ticks;
write generation alone is not process identity. Restart never loads old evidence.

## Retained evidence

Evidence contains validated request fields (including exact argv), process,
start/finish times, plan pre InvocationID and target fingerprint, effect and
permit/execution IDs, canonical policy decision/reason, replay flag, execution
exit status, post InvocationID/target, full structured verifier facts and reason,
cleanup facts and terminal outcome when available. Null/absent means unavailable,
not success. IDs from a plan are proposed bindings, not proof of journal claims.
Execution identity state is projected from the canonical result/journal; when
post-observation raises, already durable execution status is read from that
journal without claiming or updating anything. Exception type only is retained;
stdout, stderr, arbitrary exception text and environment are excluded.
The latest evidence survives empty cycles and process restarts but is replaced
by the next processed request, including malformed/denied requests. It does not
replace canonical durable replay protection or historical execution journals.

## Atomicity and failure

Writes use private 0600 exclusive temporary files in an owner-controlled,
non-group/world-writable runtime directory, file fsync, atomic replace and
directory fsync. Final-component symlinks are not followed. Readers see complete
old or new JSON. State and evidence are separate atomic records, not a transaction;
terminal evidence is persisted before terminal state. Persistence failure cannot
produce successful new terminal proof and latches the aggregate false. A stale
PROCESSING record cannot be accepted as idle proof. Idle write failure propagates
to the existing runtime error handling. Missing Linux identity prevents proof.

## Deployment separation

Passing repository tests requires Architecture Authority review. Deployment
requires new explicit Commander approval for exactly one Sentinel restart.
Previous D7D.2C effect approval is not reusable. After deployment and verified
idle projection, a fresh live-effect approval is required.
