# AIRIV Sentinel — Incident Lifecycle & Final Outcome Contract V2

## 1. Purpose

This contract defines the canonical Incident lifecycle and final outcome semantics
for AIRIV Sentinel Autonomous Commander.

This contract is a design boundary only.

No production implementation is authorized by this document alone.

---

## 2. Canonical Incident Lifecycle

An Incident has exactly three lifecycle states:

```text
OPEN
  ↓
INVESTIGATING
  ↓
TERMINAL
