#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: install_systemd_service.sh [--apply] [--user USER] [--group GROUP]
                                  [--repo PATH] [--python PATH]
Default: render and display installation commands only (dry run).
--apply: requires existing root privileges; install unit and reload definitions.
Default service user: current user, or non-root SUDO_USER when running as root.
Direct root invocation requires --user USER. Group defaults to that user's group.
Service activation is a separate Phase 2.7 operation.
HELP
}
apply=false
service_user=''
service_group=''
user_set=false
group_set=false
render_args=()
while (( $# )); do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --apply) apply=true; shift ;;
        --user|--group|--repo|--python)
            if (( $# < 2 )); then printf 'Missing value for %s\n' "$1" >&2; exit 1; fi
            case "$1" in
                --user) service_user=$2; user_set=true ;;
                --group) service_group=$2; group_set=true ;;
                *) render_args+=("$1" "$2") ;;
            esac
            shift 2 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
effective_uid=$(id -u)
if "$apply" && [[ "$effective_uid" != 0 ]]; then
    fail 'Apply requires existing root privileges.'
fi
if ! "$user_set"; then
    if [[ "$effective_uid" == 0 ]]; then
        service_user=${SUDO_USER:-}
        [[ -n "$service_user" && "$service_user" != root ]] ||
            fail 'Running as root requires --user USER or a valid non-root SUDO_USER.'
    else
        service_user=$(id -un)
    fi
fi
[[ "$service_user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]] || fail 'Invalid or empty service user'
[[ "$service_user" != root ]] || fail 'A non-root service user is required'
service_uid=$(id -u "$service_user") || fail 'Unknown service user; specify --user USER.'
[[ -n "$service_uid" && "$service_uid" != 0 ]] || fail 'A non-root service user is required'
if ! "$group_set"; then
    service_group=$(id -gn "$service_user") || fail 'Cannot determine service group'
fi
render_args+=(--user "$service_user" --group "$service_group")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
staging=$(mktemp -d /tmp/airiv-sentinel-install.XXXXXXXX)
trap 'rm -f -- "$staging/airiv-sentinel.service"; rmdir -- "$staging"' EXIT
unit="$staging/airiv-sentinel.service"
target=/etc/systemd/system/airiv-sentinel.service
"$script_dir/render_systemd_service.sh" "${render_args[@]}" --output "$unit"
printf 'Target: %s\n' "$target"
if "$apply"; then
    install -o root -g root -m 0644 -- "$unit" "$target"
    systemctl daemon-reload
else
    printf 'DRY RUN — HOST NOT MODIFIED\n'
    printf 'Intended commands (temporary render is removed on exit):\n'
    printf 'install -o root -g root -m 0644 -- %q %q\n' "$unit" "$target"
    printf 'systemctl daemon-reload\n'
fi
