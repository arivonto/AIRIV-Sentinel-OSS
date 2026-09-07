# Diagnostic Evidence Generation V1

Hypothesis generation is not diagnosis. `EvidenceHypothesisGenerator.generate`
reads canonical persisted Investigation Observations through InvestigationStore
and returns canonical Hypothesis values. No parallel evidence store exists.

The existing EvidenceAdapter copies incident EvidenceRecord facts into Investigation
observations at registration, retaining the original evidence ID (scoped by the
investigation and its incident), timestamp and exact component association.
No raw terminal content is copied. Sensor observations have no diagnostic action;
the canonical required action-ID string is empty.

V1 supports only TMUX pane identity plus an explicit boolean `pane_dead=True`.
The candidate states only that the pane was observed terminated. It asserts no
root cause, application failure cause, or remediation requirement. Explicit direct
support sets HypothesisStatus.SUPPORTED; this is not an established Diagnosis.
Missing evidence, unsupported sources, malformed facts, identity mismatches and
mixed true/false liveness observations fail closed with no candidate. Capture
failure, command identity and first-observation flags alone are insufficient.

Every candidate references an actual persisted observation also registered in the
Investigation evidence IDs. Identity is a stable SHA-256 of rule version,
investigation, incident and component. Equivalent unchanged evidence yields the
same logical candidate; the engine persists only new IDs. Repeated cycles and
repeated identical facts cannot grow duplicate hypotheses. Canonical timestamps
come from the earliest supporting observation. IDs, enums, timestamps and evidence
relationships survive persistence and reload.

Generation runs at the existing diagnostic boundary before evaluation, never for
inactive or action/risk-exhausted investigations. Existing action budget checks,
reservations, counters and terminal transitions remain authoritative. Generation
consumes no diagnostic action and cannot extend budgets.

DiagnosisEvaluator remains the exclusive diagnosis authority with unchanged
thresholds. No evidence means no hypothesis and no fabricated diagnosis. The
generator has no semantic, Commander, remediation, execution, verification or
incident-resolution authority. Production semantic policy and remediation catalog
remain empty; existing unconfigured policy behavior is unchanged.

V1 is headless, deterministic and local: no external AI/LLM, network dependency,
subprocess, shell command execution, service mutation or host operation.
