# AIRIV Sentinel — Production Systemd Controlled Activation Contract V1

## Phase

2.13D.D8.10A

## Purpose

Define immutable, explicit and time-bounded activation evidence for a
future controlled production-systemd remediation invocation.

D8.10A defines data semantics only.

It does not activate runtime execution.

## Activation Grant

A grant must bind exactly:

- activation ID;
- machine approval ID;
- incident ID;
- component ID;
- execution ID;
- effect fingerprint;
- issuance time;
- expiry time.

No wildcard, target family, service class, or reusable global
activation is permitted.

## Approval ID

The approval ID is a machine identifier.

Human-language approval text is not used directly as the machine
approval ID.

## Expiration

Every grant must expire.

`expires_at` must be strictly greater than `issued_at`.

At assessment time:

`issued_at <= now < expires_at`

must hold.

Expired or not-yet-valid grants fail closed.

## Exact Effect Binding

The activation grant must exactly match:

- incident ID;
- component ID;
- execution ID;
- effect fingerprint.

Any mismatch fails closed.

## Meaning of Eligible

`activation_binding_valid` means only that the activation evidence is
structurally valid, active in time, and exactly bound to the supplied
effect identity.

It does NOT mean:

- RemediationPolicy ALLOW;
- target allowlisted;
- permit granted;
- runtime layers enabled;
- execution authorized by the host;
- execution started.

## Authority Separation

D8.10A MUST NOT:

- mutate D8.9D enabled state;
- mutate D8.9C enabled state;
- mutate D8.9A enabled state;
- invoke D8.9D;
- invoke D8.9B;
- call remediation policy;
- call production target policy;
- call production runtime guard;
- claim permit;
- write attempt ledger;
- acquire effect lease;
- execute;
- verify;
- resolve an incident.

## Persistence

D8.10A introduces no durable activation store.

The contract is an immutable in-memory value boundary only.

Durable single-use consumption semantics require a separate future
milestone.

## Runtime

`SentinelRuntime` MUST NOT own a default activation grant.

`SentinelRuntime.run_once()` MUST NOT inspect activation grants.

All existing runtime execution layers remain disabled.

## Host State

No unit file, polkit rule, service, process, or host authorization is
changed by D8.10A.

## Commander Gate

No Commander approval is required to implement or test this inert
contract.

A fresh explicit Commander approval will be required before any later
milestone actually enables a host-affecting production remediation
path.
