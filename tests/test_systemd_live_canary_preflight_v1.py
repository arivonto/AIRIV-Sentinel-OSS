from __future__ import annotations

import inspect

import pytest

import sentinel.systemd_live_canary_preflight as module

from sentinel.systemd_live_canary_preflight import (
    CANARY_COMPONENT_ID,
    CANARY_FRAGMENT_PATH,
    CANARY_UNIT,
    CANARY_UNIT_TEXT,
    POLKIT_MANAGE_UNITS,
    SENTINEL_UNIT,
    SystemdCanaryDesign,
    canonical_canary_design,
)


def test_canonical_canary_is_distinct_from_sentinel():
    design = canonical_canary_design()

    assert (
        design.unit_name
        == CANARY_UNIT
    )

    assert (
        design.unit_name
        != SENTINEL_UNIT
    )

    assert (
        design.component_id
        == CANARY_COMPONENT_ID
    )

    assert (
        design.component_id
        != "systemd:"
        + SENTINEL_UNIT
    )

    assert (
        design.fragment_path
        == CANARY_FRAGMENT_PATH
    )

    assert (
        "airiv-sentinel.service"
        not in design.unit_text
    )


def test_canary_workload_is_inert_and_no_shell():
    design = canonical_canary_design()

    assert (
        "ExecStart=/usr/bin/sleep infinity"
        in design.unit_text
    )

    assert (
        "Restart=no"
        in design.unit_text
    )

    forbidden = (
        "/bin/bash",
        "/bin/sh",
        "sudo ",
        "pkexec ",
        "-m sentinel",
        "curl ",
        "wget ",
        "nc ",
        "socat ",
    )

    lowered = (
        design.unit_text.lower()
    )

    for token in forbidden:
        assert (
            token.lower()
            not in lowered
        )


def test_canary_contains_required_hardening():
    required = (
        "DynamicUser=yes",
        "NoNewPrivileges=yes",
        "PrivateTmp=yes",
        "ProtectSystem=strict",
        "ProtectHome=yes",
        "ProtectKernelTunables=yes",
        "ProtectKernelModules=yes",
        "ProtectControlGroups=yes",
        "RestrictSUIDSGID=yes",
        "LockPersonality=yes",
        "MemoryDenyWriteExecute=yes",
    )

    for value in required:
        assert value in CANARY_UNIT_TEXT


def test_candidate_restart_argv_is_exact_no_shell():
    design = canonical_canary_design()

    assert (
        design.candidate_restart_argv
        == (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            CANARY_UNIT,
        )
    )


def test_design_rejects_sentinel_identity():
    with pytest.raises(
        ValueError,
    ):
        SystemdCanaryDesign(
            unit_name=SENTINEL_UNIT,

            component_id=(
                "systemd:"
                + SENTINEL_UNIT
            ),

            fragment_path=(
                "/etc/systemd/system/"
                + SENTINEL_UNIT
            ),

            executable=(
                "/usr/bin/sleep"
            ),

            unit_text=(
                CANARY_UNIT_TEXT
            ),
        )


def test_unit_hash_and_design_fingerprint_are_stable():
    first = canonical_canary_design()
    second = canonical_canary_design()

    assert (
        first.unit_sha256
        == second.unit_sha256
    )

    assert (
        first.fingerprint
        == second.fingerprint
    )

    assert len(
        first.unit_sha256
    ) == 64

    assert len(
        first.fingerprint
    ) == 64


def test_polkit_probe_is_noninteractive_by_omission(
    monkeypatch,
):
    calls = []

    class Completed:
        returncode = 1
        stdout = ""
        stderr = ""

    def fake_runner(
        argv,
        **kwargs,
    ):
        calls.append(
            (
                tuple(argv),
                kwargs,
            )
        )

        return Completed()

    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name: (
            "/usr/bin/pkcheck"
            if name == "pkcheck"
            else None
        ),
    )

    result = module._polkit_probe(
        runner=fake_runner,
        timeout=3.0,
    )

    assert result.status == "DENIED"

    assert len(calls) == 1

    argv, kwargs = calls[0]

    assert argv[0:4] == (
        "/usr/bin/pkcheck",
        "--action-id",
        POLKIT_MANAGE_UNITS,
        "--process",
    )

    subject = argv[4].split(",")

    assert len(subject) == 3

    assert subject[0] == str(
        module.os.getpid()
    )

    assert int(subject[1]) > 0

    assert subject[2] == str(
        module.os.getuid()
    )

    assert (
        "--allow-user-interaction"
        not in argv
    )

    assert not any(
        token.startswith(
            "--allow-user-interaction="
        )
        for token in argv
    )

    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["timeout"] == 3.0
    assert kwargs["check"] is False


def test_preflight_module_owns_no_systemd_mutation():
    source = inspect.getsource(
        module
    )

    # The planned future restart argv exists as immutable design data,
    # but no runner invocation may use lifecycle mutation verbs.
    runner_functions = (
        inspect.getsource(
            module._loaded_collision
        )
        + inspect.getsource(
            module._offline_verify
        )
        + inspect.getsource(
            module._sudo_probe
        )
        + inspect.getsource(
            module._polkit_probe
        )
    )

    for forbidden in (
        '"restart"',
        '"start"',
        '"stop"',
        '"enable"',
        '"disable"',
        '"daemon-reload"',
        '"reset-failed"',
        '"try-restart"',
        '"reload-or-restart"',
    ):
        assert (
            forbidden
            not in runner_functions
        )

    assert (
        "os.system"
        not in source
    )

    assert (
        "shell=True"
        not in source
    )
