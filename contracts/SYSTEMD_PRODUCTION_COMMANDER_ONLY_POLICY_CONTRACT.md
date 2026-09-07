# Commander-only production policy authorization — D8.15

COMMANDER_ONLY remains distinct from AUTONOMOUS and never becomes autonomously
eligible. `RemediationPolicy.evaluate_systemd_production_bound` accepts optional
`SystemdProductionCommanderAuthorizationContext`, default None. Missing, raw,
malformed, expired or mismatched Commander facts cannot preserve bound ALLOW
for COMMANDER_ONLY. AUTONOMOUS behavior is unchanged.

The immutable context reuses the D8.10C consumed activation/prepared binding.
Explicit trusted composition constructs it with canonical D8.14 issuer and
D8.10B store instances, checking exact committed issuance and consumption
records through their existing readers. The context is a trusted in-process
snapshot, not an untrusted parser or authentication mechanism. Storage roots
must be supplied by trusted composition, never request input. Durable ledgers
are append-only; this milestone introduces no revocation or record reclamation.
Neither a raw approval ID nor a raw grant proves durable issuance/consumption.

Policy consumes only pure facts: current grant and evidence, exact canonical
prepared plan, incident, component/target, action, effect fingerprint, execution,
run, scope and permit binding. It revalidates D8.10C continuity and canonical
plan construction. The context neither issues nor consumes approvals and makes
no ALLOW/DENY decision. D8.14 issuance and D8.10 consumption/binding ownership
remain unchanged. Policy does no persistence or execution.

RemediationPolicy remains the sole ALLOW/DENY authority. Existing action and
exact bound-effect authorization remain mandatory and are evaluated once;
Commander facts cannot upgrade their DENY. Target must be known, unprotected,
live eligible and COMMANDER_ONLY, with cooldown, retry budget, blast radius and
mandatory verification satisfied. Approval alone grants no execution authority.

D8.4 remains mandatory: effect lease and durable attempt facts surround policy,
attempt reservation follows ALLOW before execution, and existing identity,
permit, fingerprint and verification boundaries retain their ownership/order.
No shortcut or Commander context forwarding is added to integration or runtime.

Production allowlist remains empty. D8.10D activation bridge, D8.9D runtime
bridge, D8.9C invocation surface and D8.9A dispatch gate remain disabled.
D8.15 alone grants no execution authority, makes no live request/effect and
requires no deployment reload. Runtime wiring is a separate future milestone.
