# AIRIV Sentinel — Systemd Canary Installation Safety Plan

## Phase

2.13D.D7B

## Purpose

Define the exact future installation, activation, rollback, and
pre-mutation authorization contract for:

`airiv-sentinel-remediation-canary.service`

D7B performs no host mutation.

## D7A Dependency

D7B requires the D7A canary design to remain:

- collision-free;
- distinct from `airiv-sentinel.service`;
- offline-verifiable;
- inert;
- shell-free;
- network-free;
- disposable.

## Exact File Manifest

Destination:

`/etc/systemd/system/airiv-sentinel-remediation-canary.service`

Required ownership:

- uid: 0
- gid: 0

Required mode:

`0644`

Content must exactly equal the canonical D7A `CANARY_UNIT_TEXT`.

The content SHA-256 and design fingerprint are immutable plan fields.

No alternate unit content may be substituted after authorization.

## Planned Installation Sequence

Future installation authority must perform, in order:

1. securely stage exact canonical unit bytes;
2. verify staged SHA-256;
3. install exact file to exact destination with root:root / 0644;
4. verify destination bytes, ownership, mode and inode metadata;
5. execute:
   `/usr/bin/systemctl --no-ask-password daemon-reload`
6. independently inspect exact canary identity;
7. execute:
   `/usr/bin/systemctl --no-ask-password start airiv-sentinel-remediation-canary.service`
8. independently verify:
   - loaded;
   - active;
   - exact fragment identity;
   - InvocationID present.

D7B only describes this sequence. It executes none of it.

## Planned Rollback / Teardown

If installation or activation fails after host mutation begins:

1. stop the canary if loaded/active:
   `/usr/bin/systemctl --no-ask-password stop airiv-sentinel-remediation-canary.service`
2. remove only the exact canary fragment;
3. execute:
   `/usr/bin/systemctl --no-ask-password daemon-reload`
4. execute:
   `/usr/bin/systemctl --no-ask-password reset-failed airiv-sentinel-remediation-canary.service`
5. verify:
   - fragment absent;
   - LoadState is `not-found`;
   - Sentinel service identity unchanged.

Rollback must never touch `airiv-sentinel.service`.

## Pre-Mutation Gate

Host mutation is forbidden unless ALL are true:

1. D7A `design_ready == True`;
2. canary fragment collision is false;
3. loaded-unit collision is false;
4. exact design fingerprint matches installation plan;
5. exact unit SHA-256 matches installation plan;
6. privilege result is `AUTHORIZED`;
7. explicit Commander approval token is exactly:

   `APPROVE CANARY INSTALL 2.13D.D7C`

Anything else is fail-closed.

## Approval Scope

The approval token above authorizes only future installation and initial
activation of the dedicated canary.

It does NOT authorize:

- restart of `airiv-sentinel.service`;
- restart of any production service;
- arbitrary systemd changes;
- canary restart remediation itself.

The first actual canary remediation restart requires a separate later
Commander gate.

## D7B Hard Stop

D7B MUST NOT:

- write below `/etc/systemd/system`;
- run `systemctl daemon-reload`;
- run `systemctl start`;
- run `systemctl stop`;
- run `systemctl restart`;
- run `systemctl reset-failed`;
- invoke sudo or pkexec for mutation;
- claim remediation permit;
- claim execution identity.

D7B produces immutable planning data only.
