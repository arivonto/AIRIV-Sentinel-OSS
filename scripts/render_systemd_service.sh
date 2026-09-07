#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'HELP'
Usage: render_systemd_service.sh [--user USER] [--group GROUP] [--repo PATH]
                                 [--python PATH] [--output PATH]
Render the foreground python -m sentinel service without changing the host.
Defaults: current user/group, repository containing this script, repo/venv/bin/python.
Output must be a new file; defaults to a private directory under /tmp.
HELP
}
fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo=$(cd -- "$script_dir/.." && pwd -P)
service_user=$(id -un)
service_group=$(id -gn)
python_path=''
output=''
python_set=false
output_set=false
while (( $# )); do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --user|--group|--repo|--python|--output)
            (( $# >= 2 )) || fail "Missing value for $1"
            case "$1" in
                --user) service_user=$2 ;;
                --group) service_group=$2 ;;
                --repo) repo=$2 ;;
                --python) python_path=$2; python_set=true ;;
                --output) output=$2; output_set=true ;;
            esac
            shift 2 ;;
        *) fail "Unknown option: $1" ;;
    esac
done
# Restrict account names to literal systemd identities, with no specifier expansion.
[[ "$service_user" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]] || fail 'Invalid or empty user'
[[ "$service_group" =~ ^[a-zA-Z_][a-zA-Z0-9_-]*\$?$ ]] || fail 'Invalid or empty group'
[[ "$service_user" != root ]] || fail 'A non-root service user is required'
[[ -d "$repo" ]] || fail 'Repository must be an existing directory'
repo=$(cd -- "$repo" && pwd -P)
if ! "$python_set"; then python_path="$repo/venv/bin/python"; fi
[[ -f "$python_path" && -x "$python_path" ]] || fail 'Python executable must exist and be executable'
# Keep the venv executable path (do not resolve its symlink).
[[ "$python_path" == /* ]] || python_path="$PWD/$python_path"
template="$script_dir/../deployment/systemd/airiv-sentinel.service.in"
[[ -f "$template" ]] || fail 'Service template is missing'
if "$output_set"; then
    [[ -n "$output" ]] || fail 'Output must not be empty'
else
    output="$(mktemp -d /tmp/airiv-sentinel-render.XXXXXXXX)/airiv-sentinel.service"
fi
# Encode unit syntax, including spaces and specifiers. ExecStart additionally
# escapes dollar expansion. Reject control characters rather than adding lines.
escape_path() {
    local value=$1
    [[ ! "$value" =~ [[:cntrl:]] ]] || fail 'Control characters are not supported in paths'
    value=${value//\\/\\\\}
    value=${value// /\\x20}
    value=${value//\"/\\\"}
    value=${value//\'/\\\'}
    value=${value//%/%%}
    REPLY=$value
}
escape_path "$repo"
rendered_repo=$REPLY
escape_path "$python_path"
rendered_python=${REPLY//\$/\$\$}
# Literal per-line replacement avoids replacement-language interpretation.
# Noclobber also refuses symlinks and existing files.
set -o noclobber
{
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            'User=@SERVICE_USER@') printf 'User=%s\n' "$service_user" ;;
            'Group=@SERVICE_GROUP@') printf 'Group=%s\n' "$service_group" ;;
            'WorkingDirectory=@REPO_ROOT@') printf 'WorkingDirectory=%s\n' "$rendered_repo" ;;
            'ExecStart=@PYTHON_EXECUTABLE@ -m sentinel') printf 'ExecStart=%s -m sentinel\n' "$rendered_python" ;;
            *) printf '%s\n' "$line" ;;
        esac
    done < "$template"
} > "$output"
printf 'Rendered: %s\n' "$output"
