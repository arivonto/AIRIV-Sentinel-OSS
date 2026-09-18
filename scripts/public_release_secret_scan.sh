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

# Historical source versions belong in Git history, not beside canonical files.
mapfile -t backup_files < <(
    git ls-files | grep -E '(^|/).*(\.bak([._-]|$)|\.pre_|\.identity_backup\.|~$|\.orig$|\.rej$)' || true
)

if (( ${#backup_files[@]} )); then
    printf 'Tracked backup/scratch files detected:\n' >&2
    printf ' - %s\n' "${backup_files[@]}" >&2
    fail 'remove tracked backup/scratch files before public release'
fi
printf 'CURRENT_TREE_BACKUP_HYGIENE=PASS\n'

# Filenames that are commonly secret-bearing. Fail closed even when their
# current content happens not to match a known token pattern.
mapfile -t forbidden_files < <(
    git ls-files | grep -E '(^|/)(\.env($|\.)|credentials\.json$|secrets\.json$|auth\.json$|service-account[^/]*\.json$|\.netrc$|\.npmrc$|kubeconfig$|id_rsa$|id_ed25519$)|\.(pem|key|p12|pfx|jks|keystore|token|secret)$' || true
)
if (( ${#forbidden_files[@]} )); then
    printf 'Forbidden secret-bearing filename(s) tracked:\n' >&2
    printf ' - %s\n' "${forbidden_files[@]}" >&2
    fail 'forbidden secret-bearing filename tracked'
fi
printf 'CURRENT_TREE_SECRET_FILENAMES=PASS\n'

# High-confidence credential patterns. Candidate values are never printed.
patterns=(
    '-----BEGIN ([A-Z0-9]+ )*PRIVATE KEY-----'
    'gh[pousr]_[A-Za-z0-9_]{20,}'
    'github_pat_[A-Za-z0-9_]{20,}'
    'glpat-[A-Za-z0-9_-]{20,}'
    'AKIA[0-9A-Z]{16}'
    'AIza[0-9A-Za-z_-]{35}'
    'sk-[A-Za-z0-9_-]{24,}'
    'xox[baprs]-[A-Za-z0-9-]{10,}'
    'npm_[A-Za-z0-9]{30,}'
    'pypi-[A-Za-z0-9_-]{40,}'
    'ya29\.[A-Za-z0-9_-]{20,}'
    'https?://[^[:space:]/:@]+:[^[:space:]@/]+@'
)

mapfile -t commits < <(git rev-list --all)
(( ${#commits[@]} > 0 )) || fail 'no reachable commits found'

# Scan each reachable blob once. The previous commit/pattern nested loop
# re-read the same historical content thousands of times on long-lived repos.
combined_pattern=$(IFS='|'; printf '%s' "${patterns[*]}")
declare -A scanned_blobs=()
hits=0
while IFS= read -r object_id path; do
    [[ -n "$object_id" && -n "$path" ]] || continue
    [[ "$path" == 'scripts/public_release_secret_scan.sh' ]] && continue
    [[ -n "${scanned_blobs[$object_id]+x}" ]] && continue
    scanned_blobs["$object_id"]=1

    if git cat-file blob "$object_id" | grep -I -q -E "$combined_pattern"; then
        hits=1
        printf 'Potential credential pattern in reachable history at blob %s:\n' "$object_id" >&2
        printf ' - %s\n' "$path" >&2
    fi
done < <(git rev-list --objects --all)

(( hits == 0 )) || fail 'potential credential material exists in reachable Git history'
printf 'REACHABLE_HISTORY_HIGH_CONFIDENCE_SECRET_SCAN=PASS\n'

printf '%s\n' '============================================================'
printf '%s\n' ' PUBLIC RELEASE SECURITY / HYGIENE SCAN = PASS'
printf '%s\n' '============================================================'
