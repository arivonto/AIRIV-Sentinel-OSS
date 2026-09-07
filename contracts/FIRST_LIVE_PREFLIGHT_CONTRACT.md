# AIRIV Sentinel — First Live Remediation Preflight Contract

## Purpose

Final read-only safety gate before the first actual controlled live
remediation.

## Planned first-live experiment

An isolated TMUX server will later be created using an explicit
run-scoped socket. A deliberately short-lived workload will produce
a dead pane under `remain-on-exit`. The bound remediation effect will
later use the exact isolated socket and exact pane identity to perform
an exact `respawn-pane`.

This preflight does NOT create that workload or execute that effect.

## Required preflight evidence

1. TMUX executable resolves to an absolute executable regular file.
2. TMUX version can be queried using bounded read-only subprocess.
3. Workload executable resolves to an absolute executable regular file.
4. Candidate validation root does not already exist.
5. Candidate socket is strictly inside the isolated root.
6. Candidate socket path is short enough for UNIX-domain sockets.
7. Candidate root's nearest existing ancestor is a safe writable directory.
8. World-writable ancestor requires sticky-bit protection.
9. Validation session uses the dedicated AIRIV live-validation prefix.
10. Explicit isolated socket is distinct from any currently attached TMUX socket.
11. Critical remediation source files are regular non-symlink files.
12. SHA-256 evidence is captured for all critical remediation source files.
13. Fresh remediation policy defaults are empty.
14. Fresh remediation action catalog defaults are empty.
15. Planned remediation command is represented only as an inert argv template.
16. No policy activation occurs.
17. No catalog registration occurs.
18. No bound run is configured.
19. No permit is claimed.
20. No isolated TMUX server/session/socket is created.
21. No remediation command executes.
22. No host operational state is mutated.

## First-live boundary

Passing this preflight does NOT authorize live remediation.

After this gate passes, the first actual controlled live remediation
requires explicit Commander approval.
