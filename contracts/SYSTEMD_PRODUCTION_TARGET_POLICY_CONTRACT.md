# AIRIV Sentinel — Production Systemd Remediation Target Policy Contract V1

## 1. Purpose

This contract defines the safety boundary for deciding whether a real
production systemd service is within the scope of Sentinel remediation.

This boundary performs **target-safety assessment only**.

It MUST NOT:
- execute commands;
- call systemctl;
- create execution permits;
- mutate RemediationPolicy;
- modify polkit;
- activate remediation;
- make the canonical final ALLOW/DENY decision.

`RemediationPolicy` remains the sole canonical ALLOW/DENY authority.

---

## 2. Default-Deny

Production target configuration MUST default to an empty allowlist.

No systemd production service is eligible merely because it exists,
is unhealthy, or is discoverable by Sentinel.

Every eligible target MUST have an exact explicit rule.

---

## 3. Exact Target Identity

Rules MUST use one exact system service unit name.

V1 supports only:

`<exact-name>.service`

The following are prohibited:

- wildcards;
- glob patterns;
- regex target selection;
- template units or instances containing `@`;
- `.socket`;
- `.target`;
- `.mount`;
- `.automount`;
- `.swap`;
- `.timer`;
- `.path`;
- user-manager units.

Target policy MUST NOT expand aliases or infer related units.

---

## 4. Supported Action

V1 supports exactly one remediation action:

`RESTART`

No START, STOP, RELOAD, ENABLE, DISABLE, MASK, UNMASK, KILL,
daemon-reload, or arbitrary systemctl verb is permitted.

---

## 5. Non-Overrideable Protected Targets

The following classes MUST remain outside production-target remediation
even if configuration attempts to allowlist them:

- AIRIV Sentinel itself;
- AIRIV remediation canary;
- systemd core services;
- D-Bus;
- polkit;
- SSH;
- core network-management/firewall services.

The protected-target boundary cannot be overridden by a target rule.

---

## 6. Target Modes

An allowlisted target MUST explicitly declare one of:

- `AUTONOMOUS`
- `COMMANDER_ONLY`

`AUTONOMOUS` means the target-policy facts permit downstream
RemediationPolicy to consider autonomous execution.

It does NOT itself authorize execution.

`COMMANDER_ONLY` means the target is known and scoped but cannot be
considered autonomously eligible.

---

## 7. Cooldown

Each target rule MUST define a positive cooldown.

Any prior remediation attempt against the same exact unit/action within
the cooldown window makes autonomous eligibility false.

Cooldown is evaluated from durable attempt facts supplied to the policy.
The target policy does not own or mutate attempt storage.

---

## 8. Retry Budget

Each target rule MUST define:

- retry window;
- maximum attempts within that window.

Defaults MUST be conservative.

A consumed retry budget makes autonomous eligibility false.

No policy evaluation may itself retry remediation.

---

## 9. Blast Radius

V1 permits at most one active production systemd remediation effect.

If another production effect is active, autonomous eligibility MUST be
false.

This boundary only evaluates the supplied concurrency fact. It does not
acquire execution leases.

---

## 10. Verification Requirements

Every eligible rule MUST require:

- service remains loaded;
- service becomes active;
- systemd InvocationID changes from the expected prestate.

Verification metadata is immutable target-policy output.

The canonical verification boundary remains responsible for verifying
the real host state.

---

## 11. Fail-Closed Rules

Target assessment MUST fail closed for:

- malformed unit;
- unknown unit;
- protected target;
- unsupported action;
- invalid timestamps;
- future attempt timestamps;
- cooldown violation;
- exhausted retry budget;
- concurrent production effect;
- malformed rule.

---

## 12. Authority Invariants

The production target policy owns only:

- exact target scope;
- protected-target classification;
- autonomous-vs-Commander target mode;
- cooldown facts;
- retry-budget facts;
- blast-radius facts;
- verification requirements.

It MUST NOT duplicate authority belonging to:

- CommanderSemanticPolicy;
- CommanderIntentDecider;
- RemediationPolicy;
- RemediationActionCatalog;
- execution permit boundary;
- ExecutionBoundary;
- verification boundary;
- FinalOutcomeMapper;
- IncidentManager.

---

## 13. Host Authorization

This contract does NOT expand polkit or any other host privilege.

Host authorization for real production services remains unchanged until
a separate Commander-approved milestone explicitly authorizes it.

---

## 14. Initial Production State

At LOCK of this contract:

- production allowlist MUST remain empty;
- no real service authorization is installed;
- no real production service is restarted;
- the existing canary authorization remains separate.
