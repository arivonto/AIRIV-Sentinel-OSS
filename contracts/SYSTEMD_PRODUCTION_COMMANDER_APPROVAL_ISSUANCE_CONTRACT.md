# Commander approval durable issuance — D8.14

The inert `SystemdProductionCommanderApprovalIssuer` accepts an immutable
`TrustedSystemdProductionCommanderApproval` and an exact already-prepared
production effect. Only a trusted upstream authenticated Commander adapter may
construct this input. It is an in-process trust boundary, not authentication,
an approval-text parser, or an approval decision authority. No such adapter is
wired into runtime by this milestone.

The approval contains the canonical `ResourceBoundPermitBinding`, preserving
incident, component, action, target, effect, execution, run, scope and permit
identities. Canonical preparation reconstructs and validates exact continuity;
the supplied plan and approved binding must equal that result. Timing reuses
D8.10A finite nonnegative timestamps and `issued_at <= now < expires_at`, with
expiry strictly after issuance. Canonical evidence freshness still applies.

The default ledger is outside the repository:
`~/.local/state/airiv-sentinel-secure/systemd_production_approval_issuance`.
Explicit root injection supports isolated tests. D8.4 descriptor traversal and
private-state checks remain unchanged: directory 0700, regular record 0600,
current-user ownership, no symlinks or unsafe ancestors.

The SHA-256 approval-ID filename is exclusively reserved with O_EXCL and
O_NOFOLLOW. File and directory are fsynced before atomic replacement with a
fully written, fsynced record; the directory is fsynced again before returning
the canonical D8.10A grant. The record has schema version, approval/activation
IDs, issuance/expiry timestamps and the complete canonical effect binding.
One approval ID can issue at most once, across processes and regardless of
binding or activation-ID changes. A crash may burn an approval without returning
a grant. Partial, malformed or unsafe state blocks issuance; never auto-repair
or reclaim it. All existing records are validated before reservation.
Readers ignore `.pending-*` staging entries before opening files. Only
64-lowercase-hex SHA-256 names with the `.json` suffix are parsed as committed
records (including reservations); other unexpected names fail closed. Missing
committed entries still fail closed. Staging publication cannot expose a
transient filename to record reads.

D8.10B alone owns activation consumption. D8.10C alone owns consumed-activation
to prepared-effect binding. Neither is modified or invoked here. The issuer
constructs one D8.10A grant only after successful durable reservation/publication.
It grants no production execution authority, evaluates no policy, executes or
verifies nothing, and mutates no incident lifecycle.

Runtime remains unchanged and never calls the issuer. COMMANDER_ONLY remains
unchanged, the production allowlist remains empty, and D8.10D, D8.9D, D8.9C and
D8.9A remain disabled. No deployment reload is required for this inert addition;
future runtime integration and deployment require a separate milestone.
