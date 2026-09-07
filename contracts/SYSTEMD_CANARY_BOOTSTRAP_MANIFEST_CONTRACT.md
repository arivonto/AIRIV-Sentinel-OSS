# AIRIV Sentinel — Systemd Canary Bootstrap Manifest Contract

Phase: 2.13D.D7C.4B

Purpose:
Define immutable planning data for the future privileged bootstrap
required before the first systemd canary remediation.

D7C.4B performs no host mutation.

## Exact bootstrap artifacts

1. Sentinel hardening drop-in

Path:
/etc/systemd/system/airiv-sentinel.service.d/20-airiv-no-new-privileges.conf

Exact bytes:
[Service]
NoNewPrivileges=yes

Required metadata:
uid=0
gid=0
mode=0644

2. Canary unit

Path:
/etc/systemd/system/airiv-sentinel-remediation-canary.service

Content must exactly equal the locked D7A canonical canary unit.

Required metadata:
uid=0
gid=0
mode=0644

3. Canary polkit rule

Path:
/etc/polkit-1/rules.d/49-airiv-sentinel-canary.rules

Content must exactly equal the locked D7C.3 canary-scoped rule.

Required metadata:
uid=0
gid=0
mode=0644

## Host precondition

This bootstrap manifest is bound to a host where:

airiv-sentinel.service NoNewPrivileges=no

Target state:

NoNewPrivileges=yes

## Planned apply order

File installation occurs first using the exact manifest bytes.

Then:

1. systemctl --no-ask-password daemon-reload
2. systemctl --no-ask-password restart airiv-sentinel.service
3. verify Sentinel active
4. verify Sentinel InvocationID changed
5. verify Sentinel NoNewPrivileges=yes
6. systemctl --no-ask-password start airiv-sentinel-remediation-canary.service
7. verify exact canary identity and active state
8. verify the exact polkit rule was installed using direct final-path creation/write semantics
9. perform only D7D.1-valid synthetic polkit verification

### D7D.1 corrective polkit installation semantics

The canary `.rules` artifact MUST be created/written at its exact final path:

`/etc/polkit-1/rules.d/49-airiv-sentinel-canary.rules`

A hidden temporary file followed only by rename/move into the final `.rules`
name is prohibited as D7D.1 installation semantics. Polkit rule-reload
acceptance must not depend on a rename/move event being interpreted as
`CREATED` or `CHANGES_DONE_HINT` for the final `.rules` name.

The installed bytes, SHA-256, uid, gid, and mode remain exactly governed by
the locked manifest.

### D7D.1 synthetic pkcheck evidence boundary

`pkcheck --process PID,START_TIME,UID` is a synthetic verification surface.

D7D.1 MAY use it to prove:

- the rule was loaded and can participate in evaluation;
- exact action ID/detail matching;
- exact unit and verb action-detail matching;
- resolved `subject.user`.

D7D.1 MUST NOT claim that `pkcheck --process` proves `subject.system_unit`,
`subject.no_new_privileges`, or real systemd D-Bus authorization.

On polkit 127 those stronger properties depend on the trusted safe pidfd /
D-Bus authorization path and are therefore outside the evidentiary scope of
an explicitly supplied `pkcheck --process` subject.

The canonical least-privilege predicates remain unchanged.

Real `subject.system_unit`, `subject.no_new_privileges`, and exact systemd
authorization are validated only by the separately Commander-approved
D7D.2 real systemd D-Bus execution path.

## Planned rollback

If bootstrap fails after mutation begins:

1. stop exact canary if necessary
2. remove exact canary polkit rule
3. remove exact canary unit
4. remove exact Sentinel NoNewPrivileges drop-in
5. daemon-reload
6. restart Sentinel
7. reset-failed exact canary
8. verify all three bootstrap artifacts absent
9. verify Sentinel active

The original Sentinel unit file must never be edited.

## Runtime authorization boundary

The future polkit rule is restricted to:

action:
org.freedesktop.systemd1.manage-units

unit:
airiv-sentinel-remediation-canary.service

verb:
restart

user:
arivonto

system unit:
airiv-sentinel.service

NoNewPrivileges:
true

## Dual Commander gate

Sentinel production hardening/restart requires exactly:

APPROVE SENTINEL NNP RESTART 2.13D.D7C

Canary bootstrap requires exactly:

APPROVE CANARY INSTALL 2.13D.D7C

Both approvals are required before the combined bootstrap can execute.

Neither approval authorizes the later autonomous canary remediation
restart.

## D7C.4B hard stop

D7C.4B must not:

- write below /etc/systemd/system
- write below /etc/polkit-1/rules.d
- daemon-reload
- restart Sentinel
- start/stop/restart canary
- modify sudoers
- modify polkit
- claim remediation permit
- claim execution identity
