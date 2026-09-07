# AIRIV Sentinel — Systemd Canary Bootstrap Executor Contract

Phase: 2.13D.D7C.5

Purpose:
Validate the future privileged bootstrap workflow entirely against
injected fake boundaries.

D7C.5 performs zero host mutation.

## Authority

BootstrapExecutor owns bootstrap orchestration only.

It does not own:

- real filesystem privilege
- real systemctl execution
- polkit installation
- sudo
- pkexec
- remediation permits
- remediation execution identity

All mutable effects are delegated to injected boundaries.

## Required authorization

Execution requires an immutable BootstrapAuthorization bound to the
exact CanaryBootstrapManifest fingerprint.

The authorization may only be created when the D7C.4 dual Commander
gate is READY.

## Apply sequence

1. verify all exact destination paths are absent
2. verify Sentinel pre-state:
   - active
   - NoNewPrivileges=false
   - InvocationID present
3. install exact Sentinel NNP drop-in
4. verify exact bytes and metadata
5. install exact canary unit
6. verify exact bytes and metadata
7. install exact polkit rule
8. verify exact bytes and metadata
9. daemon-reload
10. restart Sentinel
11. independently verify:
    - Sentinel active
    - InvocationID changed
    - NoNewPrivileges=true
12. start canary
13. independently verify canary active
14. require injected bootstrap authorization verification consistent with the D7D.1 evidence boundary
15. do not treat synthetic `pkcheck --process` as proof of safe-pidfd-derived runtime authorization

## D7D.1 corrective verification boundary

The fake/injected BootstrapExecutor remains responsible only for orchestration
and deterministic failure/rollback testing.

Its injected authorization boundary MAY model the intended eventual
authorization result for test purposes, but that model is not host evidence.

For real D7D.1 validation:

- exact polkit bytes and metadata must be verified;
- the polkit rule must use direct final-path installation semantics;
- synthetic `pkcheck --process` may verify loader/action-detail/user behavior;
- D7D.1 MUST NOT claim that `pkcheck --process` proves `subject.system_unit`;
- D7D.1 MUST NOT claim that `pkcheck --process` proves
  `subject.no_new_privileges`;
- D7D.1 MUST NOT claim real systemd D-Bus authorization from synthetic
  pkcheck results.

The canonical rule MUST retain:

- exact `subject.user == "arivonto"`;
- exact `subject.system_unit == "airiv-sentinel.service"`;
- exact `subject.no_new_privileges === true`.

Those strong runtime predicates are validated through the real trusted
safe pidfd / systemd D-Bus authorization path only in separately approved
D7D.2.

## Polkit installation boundary

A production host installer MUST write/create the canary rule directly at
the exact final `.rules` destination. A hidden temporary file followed by
rename/move into the final rule path is not accepted as sufficient D7D.1
reload semantics.

This requirement belongs to the injected privileged filesystem/installation
boundary. BootstrapExecutor itself still does not own sudo, pkexec, direct
host filesystem privilege, or direct polkit installation.

## Rollback

Any failure after the first successful mutation triggers rollback.

Rollback:

1. stop canary if active
2. remove the exact polkit rule if its bytes and metadata still match
3. remove the exact canary unit if its bytes and metadata still match
4. remove the exact Sentinel NNP drop-in if its bytes and metadata match
5. daemon-reload
6. restart Sentinel
7. reset-failed canary
8. verify:
   - bootstrap files absent
   - Sentinel active
   - NoNewPrivileges=false
   - canary inactive

A changed/tampered artifact must never be blindly deleted.

If rollback cannot prove restoration, result is ROLLBACK_FAILED.

## Result states

- SUCCEEDED
- BLOCKED
- FAILED_NO_MUTATION
- ROLLED_BACK
- ROLLBACK_FAILED

## D7C.5 Hard Stop

Production module must contain no direct:

- subprocess execution
- os.system
- filesystem write
- filesystem unlink
- chmod/chown
- sudo
- pkexec

D7C.5 tests use fake in-memory boundaries only.

No real Commander approval is supplied to the host.
