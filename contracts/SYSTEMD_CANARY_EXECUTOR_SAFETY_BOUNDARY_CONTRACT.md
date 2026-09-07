# AIRIV Sentinel — Systemd Canary Executor Safety Boundary

## Phase

2.13D.D7C.2

## D7C.1 Finding

The systemd privilege blocker is NOT the pkcheck process-subject form.

PID-only, PID+start-time, and PID+start-time+UID all produced the same
result on the current host:

- polkit result requires administrative authentication;
- user interaction was intentionally disabled;
- non-interactive sudo is unavailable.

Therefore the canonical strong process subject remains desirable for
identity precision, but changing subject syntax does not grant privilege.

## Canonical Process Subject

All AIRIV non-interactive pkcheck probes use:

`PID,START_TIME,UID`

where:

- PID is the probing process PID;
- START_TIME is `/proc/<pid>/stat` field 22;
- UID is the process UID.

This prevents PID reuse ambiguity.

## Non-Interactive Classification

Without `--allow-user-interaction`:

- return code 0 => AUTHORIZED;
- explicit "authentication required" result => DENIED;
- ordinary authorization denial => DENIED;
- malformed/unrecognized/internal result => UNKNOWN.

Authentication-required is DENIED for automation purposes because the
candidate remediation path explicitly forbids interactive authentication.

UNKNOWN remains fail-closed.

## Installation Executor Safety Boundary

D7C.2 introduces a preparation boundary only.

It:

- evaluates the existing D7B pre-mutation gate;
- validates the exact plan fingerprint;
- validates the exact design fingerprint;
- validates the exact file-manifest fingerprint;
- validates exact canary-only systemd argv;
- produces an immutable execution envelope only when the gate is READY.

It does NOT:

- write the unit file;
- invoke systemctl;
- invoke sudo;
- invoke pkexec;
- claim a remediation permit;
- claim an execution identity;
- mutate systemd;
- mutate polkit;
- mutate sudoers.

## Current Host Result

Because the host requires interactive administrative authentication,
the current privilege classification is DENIED.

Therefore the installation executor safety boundary MUST refuse to
prepare a mutation envelope on the current host.

## Future Privilege Change

Any future polkit/sudoers/root-helper change is a separate privileged
host mutation and requires explicit Commander authorization.

D7C.2 does not perform or authorize that change.
