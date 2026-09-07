# AIRIV Sentinel — Systemd Service Contract V1

## 1. Purpose
Defines the canonical systemd boundary for the AIRIV Sentinel 24/7 daemon.

## 2. Runtime
Canonical entrypoint:

    python3 -m sentinel.runtime

## 3. Lifecycle
systemd MUST:
- start Sentinel automatically
- restart Sentinel after unexpected failure
- stop Sentinel cleanly
- NOT own Sentinel business logic

## 4. Boundary

    systemd
       ↓
    sentinel.runtime
       ↓
    SentinelRuntime
       ↓
    run_once()

## 5. Operational Requirements
- 24/7 operation
- automatic restart on failure
- non-interactive execution
- stdout/stderr available to systemd journal
- graceful SIGTERM handling
- no dependency on Gemini
- no modification of Mission Contract

## 6. Security Boundary
systemd configuration MUST NOT grant broader privileges than required by
the locked AIRIV Sentinel Mission Contract.

## 7. Contract Status

STATUS: LOCKED
VERSION: V1
