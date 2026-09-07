# AIRIV Sentinel — Systemd Controlled Dry-Run Contract

## Purpose

Validate production-target systemd remediation composition while
hard-stopping before durable permit claim or external effect.

## Flow

Read-only SystemdUnitSnapshot
→ BoundSystemdActionScope
→ GenericBoundRemediationEffect
→ ResourceBoundPermitBinding
→ immutable privilege preflight
→ existing temporary activation lease
→ exact RemediationPolicy evaluation
→ HARD STOP

## Authority

- RemediationPolicy remains sole ALLOW/DENY authority.
- Existing activation lease remains sole temporary activation mechanism.
- Existing execution identity journal remains sole durable permit authority.
- Existing execution boundary remains sole effect authority.
- This dry-run owns none of those authorities.

## Privilege Preflight

Candidate effect argv remains:

`/usr/bin/systemctl --no-ask-password restart <exact-unit>`

Read-only privilege signals:

- exact systemctl binary;
- uid/gid;
- `sudo -n true`;
- `pkcheck --action-id org.freedesktop.systemd1.manage-units --process <pid>`.

For pkcheck, omission of `--allow-user-interaction` is the
non-interactive form.

Privilege result:

- AUTHORIZED
- DENIED
- UNKNOWN

DENIED or UNKNOWN remains fail-closed for any future live systemd effect.

## Hard Stop

D6B MUST NOT call:

- claim_live_run_permit()
- execute_bound()
- execute_argv()
- systemctl restart
- systemctl start
- systemctl stop
- systemctl try-restart
- systemctl reload-or-restart

After the dry-run:

- no durable permit exists;
- no execution identity exists;
- policy state is restored;
- bound-run state is restored;
- action catalog is restored;
- production service identity is unchanged.
