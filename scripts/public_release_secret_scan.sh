#!/usr/bin/env bash
set -euo pipefail

fail() {
    printf 'PUBLIC RELEASE SCAN: FAIL — %s\n' "$*" >&2
    exit 1
}

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || fail 'not inside a Git repository'
cd "$repo_root"

printf '%s\n' '============================================================'
printf '%s\n' ' AIRIV SENTINEL — PUBLIC RELEASE SECURITY / HYGIENE SCAN'
printf '%s\n' '============================================================'

# Current-tree hygiene: historical source versions belong in Git history, not
# beside canonical source files in a public distribution tree.
mapfile -t backup_files < <(
    git ls-files | grep -E '(^|/).*(\.bak([._-]|$)|\.pre_|\.identity_backup\.|~$|\.orig$|\.rej$)' || true
)

if (( ${#backup_files[@]} )); then
    printf 'Tracked backup/scratch files detected:\n' >&2
    printf ' - %s\n' "${backup_files[@]}" >&2
    fail 'remove tracked backup/scratch files before public release'
fi
printf 'CURRENT_TREE_BACKUP_HYGIENE=PASS\n'

# Files that must never be tracked in the distributable tree.
mapfile -t forbidden_files < <(
    git ls-files | grep -E '(^|/)(\.env($|\.)|credentials\.json$|secrets\.json$|id_rsa$|id_ed25519$)|\.(pem|key)$' || true
)
if (( ${#forbidden_files[@]} )); then
    printf 'Forbidden secret-bearing filename(s) tracked:\n' >&2
    printf ' - %s\n' "${forbidden_files[@]}" >&2
    fail 'forbidden secret-bearing filename tracked'
fi
printf 'CURRENT_TREE_SECRET_FILENAMES=PASS\n'

# High-confidence credential patterns. This intentionally reports only commit
# IDs and filenames; candidate secret values are never echoed to CI logs.
patterns=(
    '-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----'
    'gh[pousr]_[A-Za-z0-9_]{20,}'
    'github_pat_[A-Za-z0-9_]{20,}'
    'AKIA[0-9A-Z]{16}'
    'AIza[0-9A-Za-z_-]{35}'
    'sk-[A-Za-z0-9_-]{24,}'
    'xox[baprs]-[A-Za-z0-9-]{10,}'
    'https?://[^[:space:]/:@]+:[^[:space:]@/]+@'
)

mapfile -t commits < <(git rev-list --all)
(( ${#commits[@]} > 0 )) || fail 'no reachable commits found'

hits=0
for commit in "${commits[@]}"; do
    for pattern in "${patterns[@]}"; do
        mapfile -t files < <(
            git grep -I -l -E "$pattern" "$commit" -- . \
                ':(exclude)scripts/public_release_secret_scan.sh' 2>/dev/null || true
        )
        if (( ${#files[@]} )); then
            hits=1
            printf 'Potential credential pattern at commit %s in:\n' "$commit" >&2
            printf ' - %s\n' "${files[@]}" >&2
        fi
    done
done

(( hits == 0 )) || fail 'potential credential material exists in reachable Git history'
printf 'REACHABLE_HISTORY_HIGH_CONFIDENCE_SECRET_SCAN=PASS\n'

printf '%s\n' '============================================================'
printf '%s\n' ' PUBLIC RELEASE SECURITY / HYGIENE SCAN = PASS'
printf '%s\n' '============================================================'
