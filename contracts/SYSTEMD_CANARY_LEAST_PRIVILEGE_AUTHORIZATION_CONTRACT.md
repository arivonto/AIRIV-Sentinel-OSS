# AIRIV Sentinel — Canary Least-Privilege Authorization Contract

## Phase

2.13D.D7C.3

## Purpose

Define the minimum future host authorization required for the first
systemd remediation validation.

D7C.3 performs no host privilege or systemd mutation.

## Security Model

Privilege is separated into two domains.

### 1. Bootstrap Administration

Canary installation is a one-time Commander-controlled administrative
operation.

Bootstrap includes:

- installation of the exact canary unit;
- systemd daemon reload;
- initial canary start;
- installation of the exact polkit rule.

AIRIV Sentinel itself receives no autonomous permission to:

- write `/etc/systemd/system`;
- write `/etc/polkit-1/rules.d`;
- manage arbitrary unit files;
- reload the systemd manager;
- start arbitrary services;
- stop arbitrary services.

Bootstrap therefore remains outside normal Sentinel autonomous
remediation authority.

### 2. Runtime Remediation

After bootstrap, AIRIV Sentinel may eventually receive exactly one
non-interactive runtime privilege:

`restart airiv-sentinel-remediation-canary.service`

The authorization must match ALL of:

- action:
  `org.freedesktop.systemd1.manage-units`
- unit:
  `airiv-sentinel-remediation-canary.service`
- verb:
  `restart`
- user:
  `arivonto`
- originating system unit:
  `airiv-sentinel.service`
- `NoNewPrivileges` subject property:
  `true`

No wildcard unit is allowed.

No `start`, `stop`, `reload`, `try-restart`, or other systemd verb is
granted by this rule.

No privilege is granted for:

- `org.freedesktop.systemd1.manage-unit-files`
- `org.freedesktop.systemd1.reload-daemon`
- arbitrary systemd units
- arbitrary users
- interactive shell sessions.

## Why System Unit Binding Matters

The runtime rule must authorize the AIRIV Sentinel daemon identity,
not every process owned by the Unix account.

A shell process running as `arivonto` must therefore not satisfy the
runtime authorization rule.

## NoNewPrivileges Requirement

The preferred runtime rule additionally requires the requesting
Sentinel system service to have `NoNewPrivileges=yes`.

If the production Sentinel unit does not currently satisfy that
condition, runtime authorization is NOT READY.

Changing the Sentinel systemd hardening configuration is a separate
host mutation and requires Commander authorization.

## Polkit Rule

Canonical future path:

`/etc/polkit-1/rules.d/49-airiv-sentinel-canary.rules`

Required ownership:

- root:root

Required mode:

- 0644

The rule must use ES5-compatible JavaScript.

The rule may return `polkit.Result.YES` only for the exact runtime
predicate above.

All nonmatching requests return `polkit.Result.NOT_HANDLED`.

## Fail-Closed Rule

D7C.3 MUST NOT make current privilege status AUTHORIZED.

The current host remains DENIED until an explicitly authorized future
bootstrap operation changes the host configuration and subsequent
validation proves the exact rule is active.

## D7C.3 Hard Stop

Forbidden in this phase:

- writing `/etc/polkit-1/rules.d`;
- writing `/etc/systemd/system`;
- `systemctl daemon-reload`;
- `systemctl start`;
- `systemctl stop`;
- `systemctl restart`;
- sudo mutation;
- pkexec mutation;
- permit claim;
- execution identity claim.
