# Why AIRIV Sentinel

AIRIV Sentinel grew from the practical need for a Linux command station that can operate continuously, observe real system state, preserve useful incident evidence, and remain understandable to its human operator.

## The Problem

Modern development environments are often always-on. A Linux workstation or server running builds, tests, AI agents, services, and pipelines does not stop at 5 PM. Yet most tooling assumes a human is always watching. When something goes wrong at 3 AM, the evidence is often gone by morning: the log rotated, the terminal scrolled away, the temporary file was cleaned up, and only a vague memory remains that "something failed."

AIRIV Sentinel exists to close that gap without introducing uncontrolled autonomy.

## Design Priorities

The project favors:

- **Local-first operation.** Sentinel runs on the machine it observes. It does not require a cloud control plane to function.
- **Controlled operating cost.** AI providers are used where they add value, but the safety of the system does not depend on one model or one paid cloud API.
- **Deterministic, auditable behavior.** Sentinel's authority chain is explicit: observation, investigation, diagnosis, Commander intent, policy evaluation, execution, verification, and evidence. Each step is typed, tested, and fail-closed.
- **Fail-closed safety.** Unknown, malformed, stale, mismatched, or unauthorized state defaults to denial. Sentinel does not guess.
- **Bounded automation.** AI may assist engineering, diagnostics, and understanding. Repository contracts, policy boundaries, tests, evidence, and Commander authority remain the source of operational truth.

## What Sentinel Is Not

The objective is not "AI that can do anything."

Sentinel is not an unrestricted autonomous agent. It does not invent its own remediation rules. It does not retry indeterminate effects. It does not bypass its own policy layer. Production-effect boundaries are crossed only when explicit authority permits it.

The objective is a practical Sentinel that can observe continuously, explain what happened, preserve evidence, and act only within locked authority boundaries.

## Current Maturity

AIRIV Sentinel is in active development. Its foundation — deterministic core runtime, incident lifecycle, remediation policy, execution identity, verification, and evidence — is established. Higher-level capabilities such as SLO enforcement are under active development and not yet production-authorized.

See the [Roadmap](AIRIV_SENTINEL_ROADMAP.md) for current status and planned capabilities.
