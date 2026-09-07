# AIRIV Sentinel — Execution Contract V1

## 1. Purpose
Defines the canonical boundary for Sentinel system command execution.

## 2. Canonical Flow

    SentinelRuntime
        ↓
    ExecutionBoundary
        ↓
    System Command
        ↓
    Result
        ↓
    Evidence Trail

## 3. Execution Rules

The executor MUST:
- receive an explicit command
- execute only through the canonical execution boundary
- capture stdout
- capture stderr
- capture exit code
- record execution start/end
- produce a structured execution result
- preserve execution evidence

## 4. Safety Boundary

The executor MUST NOT:
- silently modify commands
- hide execution failures
- bypass the execution boundary
- invoke Gemini
- modify the Mission Contract

## 5. Autonomous Remediation

Autonomous remediation is a higher-level capability.

Execution capability MUST NOT imply that every detected incident
may automatically execute remediation.

Remediation authorization belongs to the remediation policy layer.

## 6. Contract Status

STATUS: LOCKED
VERSION: V1
