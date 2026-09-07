from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinel.first_live_preflight import (
    run_first_live_preflight,
)
from sentinel.isolated_tmux_live_validation import (
    IsolatedTmuxValidationSpec,
)


def make_executable(
    path: Path,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        "test"
    )

    path.chmod(
        0o700
    )


def make_repo(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    source = (
        repo
        / "sentinel"
        / "first_live_preflight.py"
    )

    source.parent.mkdir()

    source.write_text(
        "critical"
    )

    return repo


def make_spec(
    tmp_path,
):
    return (
        IsolatedTmuxValidationSpec
        .for_root(
            run_id="WORKLOAD-1I",
            root_dir=str(
                tmp_path
                / "liveval"
            ),
            workload_argv=(
                str(
                    tmp_path
                    / "bin"
                    / "sleep"
                ),
                "5",
            ),
        )
    )


def runner(
    command,
    **kwargs,
):
    assert command[-1] == "-V"
    assert kwargs["timeout"] == 5.0
    assert kwargs["check"] is False
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert "shell" not in kwargs

    return SimpleNamespace(
        returncode=0,
        stdout="tmux test-version\n",
        stderr="",
    )


def prepare(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(
        tmux
    )

    make_executable(
        sleep
    )

    spec = make_spec(
        tmp_path
    )

    which_map = {
        "tmux":
            str(tmux),
    }

    result = run_first_live_preflight(
        repo_root=str(repo),
        workload_spec=spec,
        recovery_workload_argv=(
            str(sleep),
            "300",
        ),
        run_id="REMEDIATION-1I",
        runner=runner,
        which=lambda name: (
            which_map.get(name)
        ),
        environ={},
        critical_sources=(
            "sentinel/first_live_preflight.py",
        ),
    )

    return (
        result,
        repo,
        spec,
        tmux,
        sleep,
    )


def test_read_only_preflight_success(
    tmp_path,
):
    result, _, spec, _, _ = prepare(
        tmp_path
    )

    assert (
        result.schema
        == "AIRIV_SENTINEL_FIRST_LIVE_PREFLIGHT_V1"
    )

    assert (
        result.run_id
        == "REMEDIATION-1I"
    )

    assert (
        result.validation_root_absent
        is True
    )

    assert (
        result.validation_socket_absent
        is True
    )

    assert (
        result.explicit_socket_isolated
        is True
    )

    assert (
        result.attached_socket_separated
        is True
    )

    assert (
        result.policy_default_empty
        is True
    )

    assert (
        result.catalog_default_empty
        is True
    )

    assert (
        result.host_mutation_performed
        is False
    )

    assert (
        result.tmux_server_started
        is False
    )

    assert (
        result.permit_claimed
        is False
    )

    assert (
        result.remediation_executed
        is False
    )

    assert not Path(
        spec.root_dir
    ).exists()


def test_planned_remediation_is_inert_template(
    tmp_path,
):
    result, _, spec, tmux, sleep = prepare(
        tmp_path
    )

    assert (
        result.planned_remediation_argv
        == (
            str(tmux.resolve()),
            "-S",
            spec.server_socket,
            "respawn-pane",
            "-k",
            "-t",
            "<BOUND_PANE_ID>",
            str(sleep.resolve()),
            "300",
        )
    )


def test_manifest_contains_source_hash(
    tmp_path,
):
    result, _, _, _, _ = prepare(
        tmp_path
    )

    assert len(
        result.source_sha256
    ) == 1

    name, digest = (
        result.source_sha256[0]
    )

    assert (
        name
        == "sentinel/first_live_preflight.py"
    )

    assert len(digest) == 64
    int(
        digest,
        16,
    )

    assert len(
        result.manifest_sha256
    ) == 64

    int(
        result.manifest_sha256,
        16,
    )


def test_existing_validation_root_fails_closed(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(tmux)
    make_executable(sleep)

    spec = make_spec(
        tmp_path
    )

    Path(
        spec.root_dir
    ).mkdir()

    with pytest.raises(
        RuntimeError,
        match="validation_root_already_exists",
    ):
        run_first_live_preflight(
            repo_root=str(repo),
            workload_spec=spec,
            recovery_workload_argv=(
                str(sleep),
                "300",
            ),
            run_id="RUN-X",
            runner=runner,
            which=lambda name: str(tmux),
            critical_sources=(
                "sentinel/first_live_preflight.py",
            ),
        )


def test_attached_socket_collision_fails_closed(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(tmux)
    make_executable(sleep)

    spec = make_spec(
        tmp_path
    )

    with pytest.raises(
        RuntimeError,
        match="isolated_socket_matches_attached_tmux",
    ):
        run_first_live_preflight(
            repo_root=str(repo),
            workload_spec=spec,
            recovery_workload_argv=(
                str(sleep),
                "300",
            ),
            run_id="RUN-X",
            runner=runner,
            which=lambda name: str(tmux),
            environ={
                "TMUX":
                    spec.server_socket
                    + ",123,0",
            },
            critical_sources=(
                "sentinel/first_live_preflight.py",
            ),
        )


def test_critical_source_symlink_rejected(
    tmp_path,
):
    repo = tmp_path / "repo"
    repo.mkdir()

    target = (
        repo
        / "actual.py"
    )

    target.write_text(
        "x"
    )

    link = (
        repo
        / "critical.py"
    )

    link.symlink_to(
        target
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(tmux)
    make_executable(sleep)

    spec = make_spec(
        tmp_path
    )

    with pytest.raises(
        RuntimeError,
        match="critical_source_symlink",
    ):
        run_first_live_preflight(
            repo_root=str(repo),
            workload_spec=spec,
            recovery_workload_argv=(
                str(sleep),
                "300",
            ),
            run_id="RUN-X",
            runner=runner,
            which=lambda name: str(tmux),
            critical_sources=(
                "critical.py",
            ),
        )


def test_tmux_version_failure_fails_closed(
    tmp_path,
):
    repo = make_repo(
        tmp_path
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(tmux)
    make_executable(sleep)

    spec = make_spec(
        tmp_path
    )

    with pytest.raises(
        RuntimeError,
        match="tmux_version_probe_nonzero",
    ):
        run_first_live_preflight(
            repo_root=str(repo),
            workload_spec=spec,
            recovery_workload_argv=(
                str(sleep),
                "300",
            ),
            run_id="RUN-X",
            runner=lambda *a, **k: (
                SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="failed",
                )
            ),
            which=lambda name: str(tmux),
            critical_sources=(
                "sentinel/first_live_preflight.py",
            ),
        )


def test_world_writable_nonsticky_ancestor_rejected(
    tmp_path,
    monkeypatch,
):
    repo = make_repo(
        tmp_path
    )

    tmux = (
        tmp_path
        / "bin"
        / "tmux"
    )

    sleep = (
        tmp_path
        / "bin"
        / "sleep"
    )

    make_executable(tmux)
    make_executable(sleep)

    spec = make_spec(
        tmp_path
    )

    real_stat = os.stat

    def fake_stat(path):
        value = real_stat(path)

        if Path(path) == tmp_path:
            return SimpleNamespace(
                st_mode=(
                    stat.S_IFDIR
                    | 0o777
                ),
                st_uid=value.st_uid,
            )

        return value

    # root parent is tmp_path; make it appear unsafe.
    with pytest.raises(
        RuntimeError,
        match="unsafe_world_writable_ancestor",
    ):
        run_first_live_preflight(
            repo_root=str(repo),
            workload_spec=spec,
            recovery_workload_argv=(
                str(sleep),
                "300",
            ),
            run_id="RUN-X",
            runner=runner,
            which=lambda name: str(tmux),
            stat_fn=fake_stat,
            critical_sources=(
                "sentinel/first_live_preflight.py",
            ),
        )


def test_preflight_does_not_create_root(
    tmp_path,
):
    result, _, spec, _, _ = prepare(
        tmp_path
    )

    assert result
    assert not Path(
        spec.root_dir
    ).exists()

    assert not Path(
        spec.server_socket
    ).exists()


def test_canonical_json_contains_no_execution_claim(
    tmp_path,
):
    result, _, _, _, _ = prepare(
        tmp_path
    )

    text = result.canonical_json()

    assert (
        '"host_mutation_performed":false'
        in text
    )

    assert (
        '"tmux_server_started":false'
        in text
    )

    assert (
        '"permit_claimed":false'
        in text
    )

    assert (
        '"remediation_executed":false'
        in text
    )
