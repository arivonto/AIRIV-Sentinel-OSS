# AIRIV Sentinel Bounded Production Pilot Contract V1

Status: **SPECIFICATION / DEFAULT-DISABLED**

## Scope

This contract defines a future bounded pilot for one Ubuntu host and one exact
target: `airiv-sentinel.service`. It does not activate the pilot or mutate the
host by itself.

## Allowed pilot

- one target service: `airiv-sentinel.service`;
- one action: restart through a separately installed least-privilege helper;
- local journal evidence only;
- cooldown: 1800 seconds;
- automatic retry budget: zero when the outcome is `UNKNOWN`;
- blast radius: one service on one host;
- verification: PID, active state, runtime identity, and journal continuity;
- rollback: manual only;
- authority expiry: seven days from activation.

## Required boundaries

The helper MUST accept only the exact unit and exact restart action. Sentinel
MUST NOT invoke unrestricted shell, arbitrary systemctl arguments, provider
calls, external delivery, or any other production mutation through this pilot.
The pilot MUST remain disabled until its decision record, helper identity,
polkit rule, evidence path, and independent verification are all validated.

Missing, stale, contradictory, or ambiguous facts MUST produce `UNKNOWN` and
MUST NOT trigger a retry or broaden the action scope.

## Non-authorizations

This contract does not authorize root access, arbitrary filesystem access,
other service units, deployment, upgrade, rollback, alert delivery outside
the local journal, or changes to the existing Sentinel service identity.
