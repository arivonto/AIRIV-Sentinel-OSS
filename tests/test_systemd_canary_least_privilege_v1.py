from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

import sentinel.systemd_canary_least_privilege as module

from sentinel.systemd_canary_least_privilege import (
    CANARY_POLKIT_RULE,
    CANARY_UNIT,
    CANARY_VERB,
    POLKIT_ACTION_MANAGE_UNITS,
    POLKIT_RULE_PATH,
    SENTINEL_UNIT,
    SENTINEL_USER,
    CanaryPolkitAuthorizationDesign,
    CanaryPolkitRequest,
    canonical_authorization_design,
    validate_canary_polkit_rule,
)


def exact_request():
    return CanaryPolkitRequest(
        action_id=(
            POLKIT_ACTION_MANAGE_UNITS
        ),

        unit=CANARY_UNIT,
        verb=CANARY_VERB,
        user=SENTINEL_USER,
        system_unit=SENTINEL_UNIT,
        no_new_privileges=True,
    )


def test_canonical_rule_offline_validates():
    design = (
        canonical_authorization_design()
    )

    assert (
        design.rule_path
        == POLKIT_RULE_PATH
    )

    assert (
        design.rule_text
        == CANARY_POLKIT_RULE
    )

    assert (
        validate_canary_polkit_rule(
            design.rule_text
        )
    )

    assert len(
        design.rule_sha256
    ) == 64

    assert len(
        design.fingerprint
    ) == 64


def test_exact_runtime_request_is_authorized_by_model():
    design = (
        canonical_authorization_design()
    )

    assert design.authorizes(
        exact_request()
    )


@pytest.mark.parametrize(
    (
        "field",
        "value",
    ),
    [
        (
            "action_id",
            (
                "org.freedesktop.systemd1."
                "reload-daemon"
            ),
        ),
        (
            "unit",
            "airiv-sentinel.service",
        ),
        (
            "unit",
            "ssh.service",
        ),
        (
            "verb",
            "start",
        ),
        (
            "verb",
            "stop",
        ),
        (
            "verb",
            "reload",
        ),
        (
            "user",
            "root",
        ),
        (
            "system_unit",
            "user@1000.service",
        ),
        (
            "system_unit",
            "",
        ),
        (
            "no_new_privileges",
            False,
        ),
    ],
)
def test_any_scope_substitution_is_denied(
    field,
    value,
):
    design = (
        canonical_authorization_design()
    )

    request = replace(
        exact_request(),
        **{
            field: value,
        },
    )

    assert not design.authorizes(
        request
    )


def test_shell_same_user_is_not_authorized():
    design = (
        canonical_authorization_design()
    )

    request = replace(
        exact_request(),
        system_unit=(
            "user-1000.slice"
        ),
    )

    assert not design.authorizes(
        request
    )


def test_rule_grants_only_one_yes_path():
    assert (
        CANARY_POLKIT_RULE.count(
            "polkit.Result.YES"
        )
        == 1
    )

    assert (
        CANARY_POLKIT_RULE.count(
            "polkit.Result.NOT_HANDLED"
        )
        == 1
    )

    # Match the complete denial statement, not the lexical
    # prefix shared by polkit.Result.NOT_HANDLED.
    assert (
        "return polkit.Result.NO;"
        not in CANARY_POLKIT_RULE
    )


def test_rule_contains_no_broad_systemd_permission():
    forbidden = (
        "manage-unit-files",
        "reload-daemon",
        '"start"',
        '"stop"',
        '"reload"',
        '"try-restart"',
        '"reload-or-restart"',
        "subject.isInGroup",
        "polkit.spawn",
        "sudo",
        "pkexec",
    )

    for token in forbidden:
        assert (
            token
            not in CANARY_POLKIT_RULE
        )


def test_rule_requires_daemon_system_unit_identity():
    assert (
        'subject.system_unit == '
        '"airiv-sentinel.service"'
        in CANARY_POLKIT_RULE
    )

    assert (
        "subject.no_new_privileges === true"
        in CANARY_POLKIT_RULE
    )


def test_manifest_is_root_owned_0644():
    design = (
        canonical_authorization_design()
    )

    assert design.owner_uid == 0
    assert design.owner_gid == 0
    assert design.mode == 0o644


def test_design_rejects_weakened_no_new_privileges_requirement():
    design = (
        canonical_authorization_design()
    )

    with pytest.raises(
        ValueError,
        match="NoNewPrivileges",
    ):
        CanaryPolkitAuthorizationDesign(
            rule_path=(
                design.rule_path
            ),

            rule_text=(
                design.rule_text
            ),

            rule_sha256=(
                design.rule_sha256
            ),

            owner_uid=0,
            owner_gid=0,
            mode=0o644,

            action_id=(
                design.action_id
            ),

            unit=design.unit,
            verb=design.verb,
            user=design.user,

            system_unit=(
                design.system_unit
            ),

            require_no_new_privileges=False,
        )


def test_module_has_no_host_mutation_authority():
    source = inspect.getsource(
        module
    )

    forbidden = (
        "subprocess",
        "os.system",
        "Popen",
        "execute_argv",
        "execute_bound",
        "claim_live_run_permit",
        "write_text",
        "write_bytes",
        "unlink",
        "chmod",
        "chown",
        "systemctl ",
        "sudo ",
        "pkexec ",
    )

    for token in forbidden:
        assert token not in source
