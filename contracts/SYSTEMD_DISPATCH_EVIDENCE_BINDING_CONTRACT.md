# Dispatch evidence continuity and freshness — 2.13D.D8.7A.1

D8.6 previously discarded trusted evidence identity, allowing distinct records
to produce equal candidate results. Its additive `trusted_evidence_identities`
tuple now retains every consumed record's canonical `record.fingerprint`,
`record.snapshot.identity.fingerprint`, `snapshot.invocation_id`, and
`observed_at`, in observation order. Existing incident/component/unit/action
fields and positional parameters are unchanged. Legacy assessments retain an
empty tuple and cannot enter the new binding boundary.

`TrustedSystemdDispatchEvidenceBinding(assessment=..., evidence=..., now=...,
max_age_seconds=...)` is frozen, pure and in-memory. It requires a candidate,
exact incident/component/unit linkage and the canonical RESTART action (records
have no action field). Exactly one retained identity must match all four facts.
The canonical evidence fingerprint additionally binds observation, investigation,
source, schema and every snapshot fact. Substituting any different record fails
closed with ValueError, even when the routing facts and candidacy are equal.
Multiple records are preserved separately; a binding validates only the supplied
record, never claims freshness for other supporting records.

Both time arguments are mandatory, with no default threshold or clock read.
`now` must be finite and non-negative; `max_age_seconds` finite and positive.
Booleans and non-numeric values are rejected. Future evidence and age greater
than the limit are rejected. Age equal to the limit is accepted. The binding
retains `validated_at`, `max_age_seconds`, exact identity, evidence, assessment,
and `expires_at = observed_at + max_age_seconds`; non-finite expiry is rejected.
`is_fresh(now)` returns false for invalid time, time before observation, or
expired evidence, and true through expiry when age remains within the limit.

D8.7A owns immutable durable evidence persistence and still accepts timestamp
zero. D8.7A.1 owns only continuity and freshness admissibility; sufficiently old
zero-timestamp evidence cannot bind. No new journal exists. Trusted callers
remain responsible for provenance and loading evidence through D8.7A; hashes
are not signatures, and neither boundary authenticates fabricated Python inputs.

D8.7B must recheck freshness at actual handoff immediately before any future
plan construction, and must reassess mutable upstream facts as required by D8.6.
D8.7B remains unimplemented here. This boundary has no policy decision, permit,
plan, execution identity, attempt ledger, lease, execution, verification or
incident lifecycle authority. Staleness rejects handoff eligibility; it never
creates a replacement RemediationPolicy decision. Production defaults stay empty.
