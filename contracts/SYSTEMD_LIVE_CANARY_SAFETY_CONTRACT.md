# AIRIV Sentinel — Systemd Live Canary Safety Contract

## Phase

2.13D.D7A

## Purpose

Define a dedicated disposable systemd canary for the first future
systemd remediation effect.

The canary exists specifically to prevent AIRIV Sentinel from using
`airiv-sentinel.service` itself as the first systemd restart target.

D7A is design and read-only preflight only.

It performs no systemd mutation.

## Canonical Canary Identity

Unit:

`airiv-sentinel-remediation-canary.service`

Canonical component:

`systemd:airiv-sentinel-remediation-canary.service`

Planned fragment:

`/etc/systemd/system/airiv-sentinel-remediation-canary.service`

Workload:

`/usr/bin/sleep infinity`

The canary must not share an identity, unit file, PID, InvocationID,
runtime state, or lifecycle with `airiv-sentinel.service`.

## Isolation Requirements

The canary:

- is a dedicated systemd service;
- has no dependency on AIRIV Sentinel;
- has no dependency from AIRIV Sentinel;
- executes no AIRIV application code;
- executes no shell;
- opens no network listener;
- writes no application data;
- uses no sudo or pkexec;
- has no restart loop;
- has no production business workload;
- is disposable;
- is independently observable through systemd state and InvocationID.

## Planned Unit Hardening

The planned canary unit uses:

- `Type=simple`
- `/usr/bin/sleep infinity`
- `Restart=no`
- `DynamicUser=yes`
- `NoNewPrivileges=yes`
- `PrivateTmp=yes`
- `ProtectSystem=strict`
- `ProtectHome=yes`
- `ProtectKernelTunables=yes`
- `ProtectKernelModules=yes`
- `ProtectControlGroups=yes`
- `RestrictSUIDSGID=yes`
- `LockPersonality=yes`
- `MemoryDenyWriteExecute=yes`

The service must not use:

- shell execution;
- sudo;
- pkexec;
- network commands;
- AIRIV Sentinel Python entrypoints;
- writable production paths.

## First Future Live Effect

The first future real systemd remediation must target the canary,
not `airiv-sentinel.service`.

Candidate effect:

`/usr/bin/systemctl --no-ask-password restart airiv-sentinel-remediation-canary.service`

That effect remains forbidden until:

1. the canary is separately installed under an explicit Commander
   authorization gate;
2. installation/start evidence is validated;
3. target identity is captured using the existing strong systemd
   identity boundary;
4. privilege preflight is AUTHORIZED rather than DENIED/UNKNOWN;
5. exact bound policy/effect/permit/execution/verifier composition passes;
6. Commander explicitly approves the first canary restart.

## Verification

Successful future restart verification requires:

- same exact canary target identity;
- unit loaded after effect;
- unit active after effect;
- a new InvocationID;
- successful execution evidence;
- independent post-effect observation.

Execution success alone is not recovery.

## D7A Hard Stop

D7A MUST NOT perform:

- file creation in `/etc/systemd/system`;
- file modification in `/etc/systemd/system`;
- `systemctl daemon-reload`;
- `systemctl enable`;
- `systemctl disable`;
- `systemctl start`;
- `systemctl stop`;
- `systemctl restart`;
- `systemctl try-restart`;
- `systemctl reload`;
- `systemctl reload-or-restart`;
- `systemctl reset-failed`;
- `sudo systemctl`;
- `pkexec systemctl`.

D7A may:

- inspect systemd read-only state;
- inspect filesystem paths;
- create temporary files below `/tmp`;
- run `systemd-analyze verify` against a temporary unit file;
- run non-interactive privilege visibility probes.

## Privilege Rule

Current live authorization remains fail-closed.

`UNKNOWN` or `DENIED` privilege status MUST NOT be treated as sufficient
for live systemd execution.
