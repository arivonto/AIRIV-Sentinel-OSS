# AIRIV Sentinel — Remediation Policy Contract V1

## 1. Purpose
Defines the authorization boundary between incident detection and
autonomous remediation.

## 2. Canonical Flow

    Detection
       ↓
    Incident
       ↓
    RemediationPolicy
       ↓
    ALLOW / DENY
       ↓
    ExecutionBoundary

## 3. Default Policy

Remediation MUST be DENIED unless an explicit policy permits it.

## 4. Policy Decision

A remediation decision MUST evaluate:
- incident state
- component identity
- remediation action
- policy authorization

## 5. Execution Boundary

The policy layer MUST NOT execute commands itself.

Execution MUST occur exclusively through ExecutionBoundary.

## 6. Evidence

Every remediation decision MUST be observable as:
- ALLOW or DENY
- reason
- incident reference
- selected action

## 7. Safety

The policy MUST NOT:
- bypass authorization
- silently alter commands
- invoke Gemini
- modify the Mission Contract

## 8. Contract Status

STATUS: LOCKED
VERSION: V1
