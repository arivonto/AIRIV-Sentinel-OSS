from __future__ import annotations

from pathlib import Path

from sentinel.polkit_noninteractive import (
    PolkitProcessSubject,
    build_pkcheck_process_argv,
    classify_pkcheck_noninteractive,
    process_start_time,
)


ACTION = (
    "org.freedesktop.systemd1.manage-units"
)


def test_strong_subject_serialization():
    subject = PolkitProcessSubject(
        pid=123,
        start_time=456,
        uid=1000,
    )

    assert (
        subject.process_argument
        == "123,456,1000"
    )


def test_exact_pkcheck_argv_uses_strong_subject():
    subject = PolkitProcessSubject(
        pid=123,
        start_time=456,
        uid=1000,
    )

    argv = build_pkcheck_process_argv(
        pkcheck_binary="/usr/bin/pkcheck",
        action_id=ACTION,
        subject=subject,
    )

    assert argv == (
        "/usr/bin/pkcheck",
        "--action-id",
        ACTION,
        "--process",
        "123,456,1000",
    )

    assert (
        "--allow-user-interaction"
        not in argv
    )


def test_authentication_required_rc2_is_denied():
    status = classify_pkcheck_noninteractive(
        returncode=2,
        stdout=(
            "polkit\\56result=auth_admin\n"
        ),
        stderr=(
            "Authorization requires authentication "
            "and -u wasn't passed."
        ),
    )

    assert status == "DENIED"


def test_rc2_without_known_auth_evidence_stays_unknown():
    status = classify_pkcheck_noninteractive(
        returncode=2,
        stdout="",
        stderr="unexpected internal error",
    )

    assert status == "UNKNOWN"


def test_rc0_authorized():
    assert (
        classify_pkcheck_noninteractive(
            returncode=0,
            stdout="",
            stderr="",
        )
        == "AUTHORIZED"
    )


def test_rc1_denied():
    assert (
        classify_pkcheck_noninteractive(
            returncode=1,
            stdout="",
            stderr="",
        )
        == "DENIED"
    )


def test_proc_stat_parser_handles_spaces_in_comm(tmp_path):
    pid = 123

    root = (
        tmp_path
        / str(pid)
    )

    root.mkdir(
        parents=True
    )

    # fields:
    # 1 pid
    # 2 comm
    # 3..21 dummy
    # 22 starttime = 777
    fields_3_to_21 = [
        "S",
        *["0"] * 18,
    ]

    raw = (
        f"{pid} "
        "(airiv test process) "
        + " ".join(
            fields_3_to_21
        )
        + " 777 "
        + "0 0 0\n"
    )

    (
        root
        / "stat"
    ).write_text(
        raw,
        encoding="utf-8",
    )

    assert (
        process_start_time(
            pid,
            proc_root=tmp_path,
        )
        == 777
    )
