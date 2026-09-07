# AIRIV Sentinel — Production Remediation Probe Design Contract V1

## Phase

2.13D.D8.12B

## Commander-Selected Exact Target

`airiv-sentinel-production-remediation-probe.service`

This selection is approved for **design only**.

D8.12B does not install, start, restart, enable, authorize, or allowlist
the unit.

---

## Purpose

Define the safest possible first non-canary target for validating the
future production systemd remediation path without placing an existing
business, network, security, storage, remote-access, desktop, or AIRIV
Sentinel workload at risk.

The D8.12A host audit found no existing service satisfying the
conservative low-dependency criteria.

Therefore the first target is a dedicated AIRIV-owned probe.

---

## Exact Identity

Unit:

`airiv-sentinel-production-remediation-probe.service`

Component:

`systemd:airiv-sentinel-production-remediation-probe.service`

Future fragment:

`/etc/systemd/system/airiv-sentinel-production-remediation-probe.service`

Only exact `.service` identity is valid.

No aliases, templates, instances, wildcards, regex, or inferred target
names are permitted.

---

## Probe Workload

The workload is deliberately non-business and non-networked:

`/usr/bin/sleep infinity`

It has no application data and no production traffic.

Restarting it must not affect:

- AIRIV Sentinel;
- Odoo;
- Docker;
- PostgreSQL;
- networking;
- Cloudflare tunnels;
- SSH;
- firewall;
- desktop session;
- security infrastructure.

---

## Unit Hardening

The planned unit reuses the already-validated canary security profile:

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
- `Restart=no`

No privileged capability is required.

---

## Future Remediation Action

Only:

`RESTART`

Canonical future argv:

`/usr/bin/systemctl --no-ask-password restart airiv-sentinel-production-remediation-probe.service`

No shell, sudo, pkexec, systemd-run, wildcard, or alternate verb is
allowed.

---

## Initial Production Target Policy Design

The first policy configuration MUST be:

- exact unit only;
- action `RESTART`;
- mode `COMMANDER_ONLY`;
- cooldown `3600` seconds;
- retry window `86400` seconds;
- maximum attempts `1`.

The target must not begin in autonomous mode.

Changing the initial target to `AUTONOMOUS` requires a later explicit
architecture milestone after controlled live validation.

---

## Future Verification

A successful remediation must verify the same exact target identity and:

1. `LoadState=loaded`;
2. `ActiveState=active`;
3. post-effect `InvocationID` differs from the pre-effect
   `InvocationID`.

Existing D8.2-D8.4 canonical verification and production runtime guard
remain authoritative.

---

## Future Host Authorization Design

Planned rule path:

`/etc/polkit-1/rules.d/49-airiv-sentinel-production-probe.rules`

The rule must authorize only:

- action ID `org.freedesktop.systemd1.manage-units`;
- unit `airiv-sentinel-production-remediation-probe.service`;
- verb `restart`;
- subject user `arivonto`;
- subject system unit `airiv-sentinel.service`;
- `subject.no_new_privileges === true`.

Everything else returns `NOT_HANDLED`.

No broad systemd authorization is permitted.

---

## Activation Issuance Design

No standing activation exists.

Each future controlled invocation requires a fresh machine
`SystemdProductionActivationGrant` bound exactly to:

- activation ID;
- Commander approval ID;
- incident ID;
- component ID;
- execution ID;
- effect fingerprint;
- issue time;
- expiry time.

Initial maximum activation lifetime:

`300 seconds`

The activation must then be durably consumed exactly once through
D8.10B and bound to the exact prepared effect through D8.10C before
D8.10D may route it downstream.

---

## Runtime Enablement

D8.12B changes no runtime enablement.

All remain disabled:

1. D8.10D activation-aware runtime bridge;
2. D8.9D runtime delegation bridge;
3. D8.9C runtime invocation surface;
4. D8.9A execution-dispatch gate.

`SentinelRuntime.run_once()` remains disconnected.

---

## Production Allowlist

The current production allowlist remains empty.

D8.12B defines a future rule but MUST NOT install it into
`RemediationPolicy`.

---

## Host State

D8.12B MUST NOT:

- create the unit file;
- run `daemon-reload`;
- start the probe;
- restart the probe;
- enable the probe;
- modify polkit;
- modify the production allowlist;
- restart Sentinel;
- execute any remediation.

---

## Next Safety Gate

Before any host installation or authorization work, a fresh Commander
approval is required.

That future approval must explicitly authorize the next bounded phase;
this D8.12B design approval is not sufficient authority for host
mutation.
