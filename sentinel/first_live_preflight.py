"""Read-only first-live controlled remediation preflight.

Phase 2.13C.1I.

This module performs host inspection only. It does not create TMUX
servers, directories, sockets, leases, policies, permits, incidents,
or remediation effects.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Mapping

from sentinel.isolated_tmux_live_validation import (
    IsolatedTmuxValidationSpec,
)
from sentinel.remediation_action_catalog import (
    RemediationActionCatalog,
)
from sentinel.remediation_policy import (
    RemediationPolicy,
)


CRITICAL_SOURCES = (
    "sentinel/live_remediation_safety.py",
    "sentinel/remediation_policy.py",
    "sentinel/remediation_action_catalog.py",
    "sentinel/execution.py",
    "sentinel/remediation_orchestrator.py",
    "sentinel/commander.py",
    "sentinel/tmux_remediation_verifier.py",
    "sentinel/tmux_server_generation_verifier.py",
    "sentinel/bound_tmux_exact_verifier.py",
    "sentinel/live_remediation_bound_composition.py",
    "sentinel/live_remediation_commander_integration.py",
    "sentinel/isolated_tmux_live_validation.py",
    "sentinel/live_remediation_activation_lease.py",
    "sentinel/controlled_live_dry_run.py",
    "sentinel/first_live_preflight.py",
)


@dataclass(frozen=True, slots=True)
class FirstLivePreflightManifest:
    schema: str

    run_id: str

    effective_uid: int
    effective_gid: int

    repo_root: str

    tmux_binary: str
    tmux_version: str

    workload_binary: str
    recovery_binary: str

    isolated_root: str
    isolated_socket: str
    isolated_session: str

    workload_argv: tuple[str, ...]
    recovery_workload_argv: tuple[str, ...]

    planned_remediation_argv: tuple[str, ...]

    attached_tmux_socket: str | None

    nearest_existing_ancestor: str
    ancestor_uid: int
    ancestor_mode: str
    ancestor_world_writable: bool
    ancestor_sticky: bool
    ancestor_write_access: bool
    ancestor_execute_access: bool

    source_sha256: tuple[tuple[str, str], ...]

    policy_allowed_actions: tuple[str, ...]
    policy_bound_runs: tuple[str, ...]

    catalog_actions: tuple[str, ...]
    catalog_triggers: tuple[str, ...]

    validation_root_absent: bool
    validation_socket_absent: bool

    explicit_socket_isolated: bool
    attached_socket_separated: bool

    policy_default_empty: bool
    catalog_default_empty: bool

    host_mutation_performed: bool
    tmux_server_started: bool
    permit_claimed: bool
    remediation_executed: bool

    manifest_sha256: str

    def canonical_dict(
        self,
    ) -> dict:
        return asdict(self)

    def canonical_json(
        self,
    ) -> str:
        return json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )


def _canonical_digest(
    payload: Mapping,
) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _required(
    value: str,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field} must be str"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field} is required"
        )

    return value


def _resolve_executable(
    value: str,
    *,
    which: Callable[[str], str | None],
    lstat_fn: Callable,
    access_fn: Callable,
) -> str:
    value = _required(
        value,
        "executable",
    )

    if os.path.isabs(value):
        resolved = str(
            Path(value).resolve(
                strict=False
            )
        )
    else:
        located = which(
            value
        )

        if not located:
            raise RuntimeError(
                f"executable_not_found:{value}"
            )

        resolved = str(
            Path(located).resolve(
                strict=False
            )
        )

    try:
        info = lstat_fn(
            resolved
        )
    except OSError as exc:
        raise RuntimeError(
            f"executable_stat_failed:{resolved}"
        ) from exc

    if stat.S_ISLNK(
        info.st_mode
    ):
        raise RuntimeError(
            f"executable_symlink_rejected:{resolved}"
        )

    if not stat.S_ISREG(
        info.st_mode
    ):
        raise RuntimeError(
            f"executable_not_regular:{resolved}"
        )

    if not access_fn(
        resolved,
        os.X_OK,
    ):
        raise RuntimeError(
            f"executable_not_executable:{resolved}"
        )

    return resolved


def _nearest_existing_ancestor(
    path: Path,
) -> Path:
    candidate = path

    while not candidate.exists():
        parent = candidate.parent

        if parent == candidate:
            raise RuntimeError(
                "no_existing_ancestor"
            )

        candidate = parent

    return candidate


def _attached_tmux_socket(
    environ: Mapping[str, str],
) -> str | None:
    value = environ.get(
        "TMUX"
    )

    if not value:
        return None

    socket = value.split(
        ",",
        1,
    )[0].strip()

    if not socket:
        return None

    return str(
        Path(socket).resolve(
            strict=False
        )
    )


def _hash_critical_sources(
    repo_root: Path,
    *,
    sources: tuple[str, ...],
    lstat_fn: Callable,
) -> tuple[tuple[str, str], ...]:
    result: list[
        tuple[str, str]
    ] = []

    for relative in sources:
        path = (
            repo_root
            / relative
        )

        try:
            info = lstat_fn(
                path
            )
        except OSError as exc:
            raise RuntimeError(
                f"critical_source_missing:{relative}"
            ) from exc

        if stat.S_ISLNK(
            info.st_mode
        ):
            raise RuntimeError(
                f"critical_source_symlink:{relative}"
            )

        if not stat.S_ISREG(
            info.st_mode
        ):
            raise RuntimeError(
                f"critical_source_not_regular:{relative}"
            )

        digest = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()

        result.append(
            (
                relative,
                digest,
            )
        )

    return tuple(result)


def run_first_live_preflight(
    *,
    repo_root: str,
    workload_spec: IsolatedTmuxValidationSpec,
    recovery_workload_argv: tuple[str, ...],
    run_id: str,
    runner: Callable = subprocess.run,
    which: Callable[[str], str | None] = shutil.which,
    lstat_fn: Callable = os.lstat,
    stat_fn: Callable = os.stat,
    access_fn: Callable = os.access,
    environ: Mapping[str, str] | None = None,
    geteuid: Callable[[], int] = os.geteuid,
    getegid: Callable[[], int] = os.getegid,
    critical_sources: tuple[str, ...] = CRITICAL_SOURCES,
) -> FirstLivePreflightManifest:
    """Perform first-live read-only validation."""

    if not isinstance(
        workload_spec,
        IsolatedTmuxValidationSpec,
    ):
        raise TypeError(
            "workload_spec must be IsolatedTmuxValidationSpec"
        )

    run_id = _required(
        run_id,
        "run_id",
    )

    repo = Path(
        _required(
            repo_root,
            "repo_root",
        )
    ).resolve(
        strict=True
    )

    if not repo.is_dir():
        raise RuntimeError(
            "repo_root_not_directory"
        )

    root = Path(
        workload_spec.root_dir
    ).resolve(
        strict=False
    )

    socket = Path(
        workload_spec.server_socket
    ).resolve(
        strict=False
    )

    if not socket.is_relative_to(
        root
    ):
        raise RuntimeError(
            "isolated_socket_outside_root"
        )

    # Fail if either path already exists OR is a dangling symlink.
    root_absent = not os.path.lexists(
        root
    )

    socket_absent = not os.path.lexists(
        socket
    )

    if not root_absent:
        raise RuntimeError(
            "validation_root_already_exists"
        )

    if not socket_absent:
        raise RuntimeError(
            "validation_socket_already_exists"
        )

    # Linux UNIX-domain socket path limit is typically 108 bytes.
    # Stay below it with margin.
    if len(
        os.fsencode(
            str(socket)
        )
    ) > 100:
        raise RuntimeError(
            "validation_socket_path_too_long"
        )

    ancestor = (
        _nearest_existing_ancestor(
            root.parent
        )
    )

    ancestor_lstat = lstat_fn(
        ancestor
    )

    if stat.S_ISLNK(
        ancestor_lstat.st_mode
    ):
        raise RuntimeError(
            "validation_ancestor_symlink_rejected"
        )

    if not stat.S_ISDIR(
        ancestor_lstat.st_mode
    ):
        raise RuntimeError(
            "validation_ancestor_not_directory"
        )

    ancestor_stat = stat_fn(
        ancestor
    )

    world_writable = bool(
        ancestor_stat.st_mode
        & stat.S_IWOTH
    )

    sticky = bool(
        ancestor_stat.st_mode
        & stat.S_ISVTX
    )

    if world_writable and not sticky:
        raise RuntimeError(
            "unsafe_world_writable_ancestor"
        )

    write_access = access_fn(
        ancestor,
        os.W_OK,
    )

    execute_access = access_fn(
        ancestor,
        os.X_OK,
    )

    if not write_access:
        raise RuntimeError(
            "validation_ancestor_not_writable"
        )

    if not execute_access:
        raise RuntimeError(
            "validation_ancestor_not_searchable"
        )

    tmux_binary = (
        _resolve_executable(
            "tmux",
            which=which,
            lstat_fn=lstat_fn,
            access_fn=access_fn,
        )
    )

    try:
        version_result = runner(
            [
                tmux_binary,
                "-V",
            ],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (
        subprocess.TimeoutExpired,
        OSError,
    ) as exc:
        raise RuntimeError(
            "tmux_version_probe_failed"
        ) from exc

    if version_result.returncode != 0:
        raise RuntimeError(
            "tmux_version_probe_nonzero"
        )

    tmux_version = (
        version_result.stdout.strip()
        or version_result.stderr.strip()
    )

    if not tmux_version:
        raise RuntimeError(
            "tmux_version_empty"
        )

    workload_binary = (
        _resolve_executable(
            workload_spec.workload_argv[0],
            which=which,
            lstat_fn=lstat_fn,
            access_fn=access_fn,
        )
    )

    if (
        not isinstance(
            recovery_workload_argv,
            tuple,
        )
        or not recovery_workload_argv
    ):
        raise ValueError(
            "recovery_workload_argv must be non-empty tuple"
        )

    recovery_binary = (
        _resolve_executable(
            recovery_workload_argv[0],
            which=which,
            lstat_fn=lstat_fn,
            access_fn=access_fn,
        )
    )

    environment = (
        os.environ
        if environ is None
        else environ
    )

    attached_socket = (
        _attached_tmux_socket(
            environment
        )
    )

    separated = (
        attached_socket is None
        or attached_socket
        != str(socket)
    )

    if not separated:
        raise RuntimeError(
            "isolated_socket_matches_attached_tmux"
        )

    source_hashes = (
        _hash_critical_sources(
            repo,
            sources=critical_sources,
            lstat_fn=lstat_fn,
        )
    )

    # Pure in-memory construction only.
    policy = RemediationPolicy()
    catalog = RemediationActionCatalog()

    policy_actions = tuple(
        sorted(
            policy.allowed_actions
        )
    )

    policy_runs = (
        policy.list_bound_runs()
    )

    catalog_actions = (
        catalog.list_actions()
    )

    catalog_triggers = (
        catalog.list_triggers()
    )

    policy_empty = (
        policy_actions == ()
        and policy_runs == ()
    )

    catalog_empty = (
        catalog_actions == ()
        and catalog_triggers == ()
    )

    if not policy_empty:
        raise RuntimeError(
            "fresh_policy_not_empty"
        )

    if not catalog_empty:
        raise RuntimeError(
            "fresh_catalog_not_empty"
        )

    planned_remediation_argv = (
        tmux_binary,
        "-S",
        str(socket),
        "respawn-pane",
        "-k",
        "-t",
        "<BOUND_PANE_ID>",
        recovery_binary,
        *recovery_workload_argv[1:],
    )

    payload = {
        "schema":
            "AIRIV_SENTINEL_FIRST_LIVE_PREFLIGHT_V1",

        "run_id":
            run_id,

        "effective_uid":
            int(
                geteuid()
            ),

        "effective_gid":
            int(
                getegid()
            ),

        "repo_root":
            str(repo),

        "tmux_binary":
            tmux_binary,

        "tmux_version":
            tmux_version,

        "workload_binary":
            workload_binary,

        "recovery_binary":
            recovery_binary,

        "isolated_root":
            str(root),

        "isolated_socket":
            str(socket),

        "isolated_session":
            workload_spec.session_name,

        "workload_argv":
            tuple(
                workload_spec.workload_argv
            ),

        "recovery_workload_argv":
            tuple(
                recovery_workload_argv
            ),

        "planned_remediation_argv":
            planned_remediation_argv,

        "attached_tmux_socket":
            attached_socket,

        "nearest_existing_ancestor":
            str(ancestor),

        "ancestor_uid":
            int(
                ancestor_stat.st_uid
            ),

        "ancestor_mode":
            oct(
                stat.S_IMODE(
                    ancestor_stat.st_mode
                )
            ),

        "ancestor_world_writable":
            world_writable,

        "ancestor_sticky":
            sticky,

        "ancestor_write_access":
            bool(
                write_access
            ),

        "ancestor_execute_access":
            bool(
                execute_access
            ),

        "source_sha256":
            source_hashes,

        "policy_allowed_actions":
            policy_actions,

        "policy_bound_runs":
            policy_runs,

        "catalog_actions":
            catalog_actions,

        "catalog_triggers":
            catalog_triggers,

        "validation_root_absent":
            root_absent,

        "validation_socket_absent":
            socket_absent,

        "explicit_socket_isolated":
            True,

        "attached_socket_separated":
            separated,

        "policy_default_empty":
            policy_empty,

        "catalog_default_empty":
            catalog_empty,

        "host_mutation_performed":
            False,

        "tmux_server_started":
            False,

        "permit_claimed":
            False,

        "remediation_executed":
            False,
    }

    digest = _canonical_digest(
        payload
    )

    return FirstLivePreflightManifest(
        **payload,
        manifest_sha256=digest,
    )
