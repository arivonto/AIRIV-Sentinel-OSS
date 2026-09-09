# AIRIV Sentinel

> **Clean open-source distribution.** This repository is the curated public source domain. Canonical private Git ancestry, private host evidence, private host-control material, credentials, authorization material, and internal release provenance are intentionally excluded.

> **Fail-closed Autonomous Commander for the AIRIV development and runtime ecosystem.**

[![AIRIV Sentinel CI](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arivonto/AIRIV-Sentinel-OSS/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Platform Linux](https://img.shields.io/badge/Platform-Linux-FCC624?logo=linux&logoColor=000000)
![Runtime systemd](https://img.shields.io/badge/Runtime-systemd-5C2D91?logo=linux&logoColor=white)
![Safety Fail Closed](https://img.shields.io/badge/Safety-Fail--Closed-critical)
![Autonomy Bounded](https://img.shields.io/badge/Autonomy-Bounded-orange)
![Canonical Regression](https://img.shields.io/badge/Canonical%20Regression-2178%20passed-success)
![Public Regression](https://img.shields.io/badge/Public%20Regression-2162%20passed-success)
![Status Pre-release](https://img.shields.io/badge/Status-Pre--release-yellow)

## Project lock — 2026-09-09

AIRIV Sentinel is a security-first autonomous operations commander. It observes runtime state, manages incidents, preserves auditable evidence, executes only explicitly authorized effects, independently verifies consequential outcomes, and performs autonomous remediation only inside bounded policy and safety contracts.

**Canonical precedence:** `Contract > Implementation > Local Preference`.

| Item | Locked / verified state |
| --- | --- |
| Target | **Autonomous Commander** |
| Strategic authority | Human Commander remains final strategic authority |
| Safety | **Fail closed / default deny** |
| V1 architecture | **FROZEN / change-controlled** |
| Runtime | Linux + systemd + Python 3.14 |
| Canonical regression | **225 focused + 2,178 full PASS** |
| Curated public regression | **225 focused + 2,162 full PASS** |
| Operational Evidence & Commander UX | **CORE COMPLETE** |
| Commander Delivery Transport Foundation | **COMPLETE** |
| External Commander delivery | **DECISION-GATED / DISABLED** |
| Provider-neutral AI execution & replay foundation | **CORE COMPLETE** |
| Live AI provider / credentials / outbound network | **DECISION-GATED / DISABLED** |
| Gate 3 | **PASSED / LOCKED** |
| Gate 4 | **BOUNDED** autonomous production-remediation profile |
| Release | Pre-release |

Validated implementation heads before this documentation closeout:

- canonical: `f1f00b582f890585311f37def53954af35a1eda6`;
- curated public: `bba2785b1549151c95dc360daa02dc7f6118f4be`.

See [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md).

## Repository topology — LOCKED

| Domain | Role | Boundary |
| --- | --- | --- |
| `AIRIV-Sentinel` | Private canonical source | contracts, implementation, tests, private operational/release/host provenance, release tooling |
| `AIRIV-Sentinel-OSS` | Curated public source | explicitly allowlisted reviewed source, contracts, docs, tests and standard deployment material |

The public repository is **not** a mirror of private Git ancestry. Publication is allowlist-based, secret-scanned, disclosure-validated and fail-closed. Publishing source grants no runtime, production, Commander or remediation authority.

## Mission and authority

Canonical mission: [AIRIV Sentinel Mission Contract V1](contracts/AIRIV_SENTINEL_MISSION_CONTRACT_V1.md).

```text
COMMANDER
  -> SENTINEL AUTHORITY POLICY
  -> AUTHORIZED EXACT EFFECT
  -> EXECUTION
  -> INDEPENDENT VERIFICATION
  -> EVIDENCE
  -> INCIDENT OUTCOME
```

Non-negotiable rules:

- `RemediationPolicy` is the canonical remediation ALLOW/DENY authority.
- `ExecutionBoundary` is the sole command-execution boundary.
- `IncidentManager.resolve()` is the sole terminal incident lifecycle mutation boundary.
- independent verification is required for consequential success claims;
- AI output is an untrusted execution/intelligence resource, never authority by itself;
- malformed, stale, mismatched, unauthorized or indeterminate effects fail closed;
- terminal uncertainty is not blindly retried.

## Canonical engineering flow

```text
Observation
-> Investigation
-> Diagnosis
-> CommanderSemanticPolicy
-> CommanderIntentAssessment
-> CommanderIntentDecider
-> RemediationPolicy
-> RemediationActionCatalog
-> Execution
-> Verification
-> FinalOutcomeMapper
-> IncidentManager.resolve()
```

No duplicate policy evaluation, execution, verification or terminal lifecycle mutation is permitted.

## Runtime specification

Canonical entrypoint:

```text
$REPO/venv/bin/python -m sentinel
```

| Property | Value |
| --- | --- |
| Worker ID | `sentinel.runtime` |
| Worker name | `Sentinel runtime` |
| Worker version | `1` |
| Daemon cycle | `1.0` second |
| Health stale threshold | `30.0` seconds |
| Process manager | systemd |
| Service restart | `Restart=on-failure`, `RestartSec=5` |
| Logging | systemd journal |
| Standard umask | `0027` |

Template: [airiv-sentinel.service.in](deployment/systemd/airiv-sentinel.service.in).

## Operational Evidence & Commander UX — CORE COMPLETE

```text
IncidentManager
-> IncidentReportBuilder
-> IncidentReportStore
-> IncidentReportRecorder
-> bounded runtime reconciliation
-> UnattendedIncidentRollup
-> CommanderAttentionQueue
-> CommanderDeliveryProjection
```

Verified behavior includes atomic report persistence, integrity metadata, idempotent reconciliation, append-retentive evidence, explicit Commander-attention derivation and exact-field disclosure projection. Reporting is read-only with respect to canonical incident lifecycle and reporting failure cannot silently disable monitoring/remediation.

## Commander Delivery Transport Foundation — COMPLETE

```text
CommanderDeliveryProjection
-> delivery identity claim
-> bound destination + transport continuity
-> RUNNING
-> transport
-> SUCCEEDED / FAILED / UNKNOWN
-> durable replay-safe outcome
```

The production default is disabled/no-send. Delivery identities are durable and replay-safe; projection digest, destination and transport identity remain bound; terminal failure/uncertainty is not blindly retried; ledger metadata excludes subject/body/raw incident evidence/credentials; deterministic local-file dry-run proves orchestration without network access. `SentinelRuntime.deliver_commander_brief()` is explicit and daemon `run_once()` does not auto-send.

**External network delivery remains disabled.** A live adapter requires exact channel and destination, credential handling, privacy/disclosure rules, bounded retries, acknowledgement semantics and separately controlled live proof.

## Verified AI Agent Operations — provider-neutral foundation CORE COMPLETE

Governing contract: [AI Agent Execution Contract V1](contracts/AIRIV_SENTINEL_AI_AGENT_EXECUTION_CONTRACT_V1.md).

Canonical provider-neutral flow:

```text
AgentRequest
-> AgentExecutionBoundary
-> replaceable AI execution resource
-> RawAgentResult
-> independent Sentinel verifier
-> append-oriented evidence
-> accepted / rejected result
```

Implemented and regression-locked:

- immutable request identity: request, agent, task, operation, execution context and authority context;
- immutable raw result identity and terminal status validation;
- production-safe disabled adapter and default-deny verifier;
- independent verification: AI self-report is not proof;
- sanitized adapter/verifier failures;
- append-oriented AI execution evidence;
- legacy `AIAgentExecutionBoundary` compatibility surface routed through the single canonical boundary;
- durable execution identity states `CLAIMED / RUNNING / SUCCEEDED / FAILED / UNKNOWN`;
- exact full-request SHA-256 continuity and replay suppression;
- incomplete or ambiguous execution can terminalize as `UNKNOWN` and is not automatically re-executed;
- durable identity ledger stores bounded metadata only, not prompts, raw model output, credentials, system commands or incident state;
- deterministic local no-network adapter + independent verifier proof;
- local proof is disabled by default and remains proposal-only.

The AI resource still owns **no** policy, lifecycle, contract, shell, Commander or remediation authority.

### Live-provider boundary — DECISION-GATED

No OpenAI, Gemini, Ollama or other provider is activated by this foundation. Before a network provider can be enabled, Sentinel still needs an explicitly reviewed provider adapter, credential source/rotation boundary, outbound-network rules, timeout/cancellation/resource budgets, rate limits/backoff, ambiguous-acknowledgement semantics, prompt/disclosure policy and controlled live proof. Consequential proposals must continue through canonical policy -> execution -> independent verification.

## Remediation levels

| Level | Meaning |
| --- | --- |
| L0 — OBSERVE | read-only observation |
| L1 — DIAGNOSE | investigation and evidence collection |
| L2 — AUTONOMOUS REMEDIATION | explicitly bounded policy-controlled effect |
| L3 — COMMANDER REQUIRED | consequential effect requiring Commander authority |

Gate 3 is **PASSED / LOCKED**. Gate 4 remains **BOUNDED**; it creates no wildcard targets, general root automation, fabricated approval or blind retry of uncertain effects.

## GitHub Actions and host authority

```text
Repository change
-> GitHub Actions validation
-> CI PASS
-> canonical main
-> separately authorized host/live workflow when required
-> trusted host boundary
-> independent verification
-> evidence
```

An ordinary push does not authorize a production effect. Documentation and source promotions in this project lock do not themselves trigger production host execution.

## Installation guide

Standard installation preserves fail-closed defaults. It does not enable autonomous production remediation, external Commander delivery or a live AI provider.

### Clone

```bash
git clone https://github.com/arivonto/AIRIV-Sentinel-OSS.git "$HOME/airiv/airiv-sentinel"
cd "$HOME/airiv/airiv-sentinel"
```

This repository is the curated public distribution.

### Environment

```bash
python3.14 -m venv venv
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements-dev.txt
```

Dependencies: [requirements-dev.txt](requirements-dev.txt).

### Validate

```bash
PYTHONPATH=. venv/bin/python -m compileall -q sentinel tests
python scripts/validate_project_docs.py
PYTHONPATH=. venv/bin/python -m pytest -q -p no:cacheprovider
bash scripts/public_release_secret_scan.sh
```

### Foreground smoke run

```bash
PYTHONPATH=. venv/bin/python -m sentinel
```

Use the reviewed standard service template for systemd installation. Production remediation, external delivery and live AI-provider enablement remain separate reviewed operations.

## Security boundary

See [SECURITY.md](SECURITY.md).

Credentials, authorization state, production evidence, private host topology and private release/deployment provenance are not public documentation. CI and curated-public validation guard against accidental disclosure.

## Roadmap lock

The [AIRIV Sentinel Roadmap](AIRIV_SENTINEL_ROADMAP.md) is change-controlled. These remain non-negotiable:

1. Commander is final strategic authority.
2. Fail-closed/default-deny behavior is mandatory.
3. Policy, execution, verification, outcome mapping and lifecycle mutation remain exclusive boundaries.
4. Evidence and replay identity are mandatory for consequential effects.
5. AI output is never authority by itself.
6. Autonomous remediation expands only through explicit bounded contracts.
7. External delivery and live AI providers remain disabled until explicitly reviewed.
8. Sentinel must not create a parallel AIRIV Event Bus or Job Worker.
9. Public distribution remains curated, not a private-history mirror.

## License

Apache License 2.0. See [LICENSE](LICENSE).
