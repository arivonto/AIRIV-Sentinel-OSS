# AIRIV Sentinel — Systemd Production Probe Live Execution Contract V1

## Phase
2.13D.D8.12E.1

## Exact target
- Unit: `airiv-sentinel-production-remediation-probe.service`
- Component: `systemd:airiv-sentinel-production-remediation-probe.service`
- Action: `RESTART`
- Canonical argv:
  `/usr/bin/systemctl --no-ask-password restart airiv-sentinel-production-remediation-probe.service`

## Commander approval binding
Only this machine approval identity is accepted:

`D8D12E-ONE-LIVE-DBUS-PROBE-RESTART`

It corresponds only to the Commander-approved D8.12E one-live-probe restart.

## Execution authority
This is a dedicated validation surface, not general production remediation authority.

Execution remains delegated through the canonical
`SystemdCommanderIntegration.execute_verified()` path.

The systemd effect must originate from the Sentinel daemon execution context.

Synthetic `pkcheck --process` MUST NOT be treated as proof of:
- `subject.system_unit`
- `subject.no_new_privileges`
- real systemd D-Bus authorization

## Exact one-shot semantics
No request means no effect.

Malformed, expired, foreign, replayed, concurrently claimed, or non-exactly
approved requests fail closed.

A completed or partially consumed request must never create a second effect
after reconstruction or daemon restart.

## Verification
Pre-effect evidence must match:
- exact target identity
- exact unit
- exact component
- loaded state
- active state
- expected InvocationID

Post-effect verification requires:
- same exact target identity
- loaded state
- active state
- new non-empty InvocationID

Execution success without successful verification is not success.

## Runtime closure
Production allowlist remains EMPTY.

These layers remain DISABLED:
1. D8.10D activation bridge
2. D8.9D runtime delegation bridge
3. D8.9C runtime invocation surface
4. D8.9A execution-dispatch gate

The D8.12E validation surface does not enable or bypass them as production
remediation authority.

## Repository-only scope
### D8.12E secure-root corrective
Root cause: `INSECURE_DEFAULT_ROOT_CONFIGURATION`. The former default
`/home/arivonto/airiv/airiv-sentinel/var/systemd_production_probe_live`
has group-writable 0775 repository ancestors, invalid for trusted durable state.

The canonical default is now
`Path.home() / ".local" / "state" / "airiv-sentinel-secure" / "systemd_production_probe_live"`.
Explicit caller-provided roots and request/state/evidence filenames are unchanged.
No path or directory security boundary is weakened. Exact target, action, argv,
approval binding, durable consumption, replay protection, and canonical execution
and verification boundaries remain unchanged; the locked canary is unchanged.

This correction is repository-only: no production state creation or migration,
live request, or live effect. Deployment reload is still required afterward;
the parent wrapper verifies host inertness, then exactly one Sentinel deployment
reload requires separate explicit Commander approval.

D8.12E.1 MUST NOT:
- create a real live request
- restart the probe
- restart Sentinel
- restart the canary
- mutate systemd
- mutate polkit
- populate the production allowlist
- enable production runtime layers

After D8.12E.1 is LOCKED, exactly one Sentinel deployment reload requires a
separate explicit Commander approval before the already-approved D8.12E probe
restart request may be delivered.
