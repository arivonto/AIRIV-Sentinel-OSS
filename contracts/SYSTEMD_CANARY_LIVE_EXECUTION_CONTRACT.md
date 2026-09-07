# Systemd canary live execution V1 — D7D.2A

Repository implementation only. This contract does not authorize deployment or
any live effect. D7D.2B requires separate Commander approval to restart Sentinel
solely to load reviewed code. D7D.2C requires fresh approval and explicit request
delivery for the first canary effect. No approval or request is shipped here.

## Request

One UTF-8 JSON object, at most 4096 bytes, with exactly these fields (no unknown
or duplicate keys). Parsing produces a frozen, slotted CanaryLiveRequest and
copies argv into an immutable tuple.

| Field | Required value or constraint |
| --- | --- |
| schema_version | Integer 1, not boolean |
| request_id | 1–64 ASCII alphanumeric, underscore or hyphen; first character alphanumeric |
| approval_id | Same bound as request_id; identifies the fresh Commander approval |
| created_at | Finite Unix timestamp in seconds, no boolean |
| expires_at | Finite Unix timestamp; created_at < expires_at <= created_at + 300 |
| component_id | `systemd:airiv-sentinel-remediation-canary.service` |
| unit | `airiv-sentinel-remediation-canary.service` |
| action | `RESTART` |
| argv | `["/usr/bin/systemctl", "--no-ask-password", "restart", "airiv-sentinel-remediation-canary.service"]` |
| expected_pre_invocation_id | Exactly 32 lowercase hexadecimal characters, nonzero |

Require created_at <= current time < expires_at at parsing and after the pre
snapshot. The approval ID is correlation, not a cryptographic signature. Delivery
is a trusted local Commander operation; possession of an arbitrary string is
not evidence of human approval outside this deployment boundary.

## Inbox and consumption

The fixed inbox is `systemd-canary-live-request.json` under
`AIRIV_SENTINEL_RUNTIME_DIR`, defaulting to repository `var/runtime`, matching
the existing runtime state root. Provision a user-owned directory without group
or other write access and publish a complete user-owned regular file with mode
0600 using atomic rename. No bootstrap or startup operation creates a request.
The state root and its ancestors are trusted deployment configuration. Final
directory and file symlinks are rejected; file hardlinks are rejected. Directory
relative operations keep consumption attached to the opened directory.

The running SentinelRuntime polls at most one file per normal cycle, synchronously
in its own process. Absence performs no snapshot, policy activation, permit claim,
execution or systemd action. Construction and start do not poll. Normal production
runs the existing foreground entrypoint in airiv-sentinel.service, so the eventual
ExecutionBoundary child inherits that service's D-Bus subject. This implementation
does not impersonate or create another unit. D7D.2B/D7D.2C must verify the actual
service user arivonto, system_unit airiv-sentinel.service and NoNewPrivileges=yes.

Consumption uses a nonblocking file lock, inode check, unlink and directory fsync
before activation or effect. A crash before execution can lose a request. Delivery
is at most once, not guaranteed execution. Malformed consumed files fail closed;
unsafe filesystem objects remain rejected. Exceptions are logged and the normal
runtime continues. The returned integration result retains execution/verification
evidence; durable execution facts remain in the existing identity journal.

## Canonical authorities and replay

An independent SystemdReadOnlyInspector snapshot must identify the exact canary
with strong identity, loaded + active, and matching pre InvocationID. It builds
one BoundSystemdRemediationPlan with ResourceBoundPermitBinding. Run ID derives
only from approval_id; execution and permit IDs derive only from request_id.
Reusing an approval with changed request/effect fails the existing durable permit
binding. Reusing a request under another approval fails the execution identity
binding. Exact replay cannot delegate a second effect, including after a crash
following the durable permit claim. No second execution ledger exists. Preserve
the existing execution identity directory and live-run permit journal across
restarts; deleting them invalidates the replay guarantee.

The policy, catalog and bound configuration must be empty before processing.
TemporaryLiveRemediationActivationLease activates only the exact plan, with no
semantic trigger registration, and restores empty state on success, denial,
execution failure, verification failure and exception. Process death discards
instance-local activation; fresh production composition is empty.

SystemdCommanderIntegration.execute_verified owns the single call to
RemediationPolicy.evaluate_bound. RemediationPolicy remains sole ALLOW/DENY
owner. GenericResourceExecutionPermitAdapter delegates through
RemediationExecutionIdentityBoundary, durable live-run permit claim,
RemediationExecutionGate and ExecutionBoundary.execute_argv. No legacy string
executor, shell wrapper, privilege elevation or alternative execution authority
is introduced. The independent post snapshot is verified by
SystemdRestartVerifier: same target identity, loaded + active, changed InvocationID.
Execution success alone is not recovery. This surface does not create or resolve
incidents or change the locked business lifecycle pipeline.

## Deployment evidence

Before any request is delivered, D7D.2B must demonstrate changed Sentinel
InvocationID, active Sentinel with NoNewPrivileges=yes, active canary with unchanged
InvocationID, no consumed request and no remediation. This phase's tests use only
fake executors and snapshots; no host remediation is authorized.
