# AIRIV Sentinel — Isolated Controlled-Live Validation Contract

## Purpose

Define the temporary workload boundary used before the first real
controlled live remediation.

## Invariants

1. Validation uses a dedicated explicit TMUX socket.
2. Validation never uses the user's/default TMUX socket.
3. Validation session names are run-scoped.
4. Validation filesystem root is run-scoped.
5. The controller owns only resources carrying its exact ownership marker.
6. Activation and teardown use typed argv with bounded subprocess timeouts.
7. No `shell=True`.
8. Activation failure triggers cleanup.
9. Context-manager exit triggers cleanup even after exceptions.
10. Teardown is idempotent.
11. Ownership mismatch fails closed.
12. Production remediation policy/catalog are not modified.
13. This phase does not execute a real live workload.
