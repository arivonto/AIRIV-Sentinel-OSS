"""Bounded pilot helper manifest regression."""

from dataclasses import replace

import pytest

from sentinel.bounded_pilot_helper_manifest import (
    HELPER_PATH,
    HELPER_TEXT,
    POLKIT_RULE_PATH,
    POLKIT_RULE_TEXT,
    SYSTEMCTL,
    BoundedPilotFileManifest,
    BoundedPilotHelperReadiness,
    canonical_bounded_pilot_helper_manifest,
    validate_bounded_pilot_polkit_rule,
)
from sentinel.bounded_pilot_readiness import (
    PILOT_ACTION,
    PILOT_HELPER_ID,
    PILOT_HELPER_SUBJECT,
    PILOT_UNIT,
)


def test_canonical_manifest_is_exact_and_stable():
    manifest = canonical_bounded_pilot_helper_manifest()

    assert manifest.helper_id == PILOT_HELPER_ID
    assert manifest.unit == PILOT_UNIT
    assert manifest.action == PILOT_ACTION
    assert manifest.subject_system_unit == PILOT_HELPER_SUBJECT
    assert manifest.helper.destination == HELPER_PATH
    assert manifest.helper.content == HELPER_TEXT
    assert manifest.polkit_rule.destination == POLKIT_RULE_PATH
    assert manifest.polkit_rule.content == POLKIT_RULE_TEXT
    assert manifest.fingerprint == (
        canonical_bounded_pilot_helper_manifest().fingerprint
    )
    assert len(manifest.fingerprint) == 64


def test_helper_invocation_and_systemctl_argv_are_exact():
    manifest = canonical_bounded_pilot_helper_manifest()

    assert manifest.invocation_argv == (
        HELPER_PATH,
        "RESTART",
        "airiv-sentinel.service",
    )
    assert manifest.systemctl_argv == (
        SYSTEMCTL,
        "--no-ask-password",
        "restart",
        "airiv-sentinel.service",
    )


def test_helper_text_accepts_only_exact_restart_request():
    assert 'EXPECTED = ("RESTART", "airiv-sentinel.service")' in HELPER_TEXT
    assert "tuple(sys.argv[1:]) != EXPECTED" in HELPER_TEXT
    assert '"--no-ask-password"' in HELPER_TEXT
    assert '"restart"' in HELPER_TEXT
    assert '"airiv-sentinel.service"' in HELPER_TEXT
    assert "os.execv(" in HELPER_TEXT

    forbidden = (
        "shell=True",
        "subprocess",
        "sudo",
        "pkexec",
        "systemd-run",
        "eval",
    )
    for token in forbidden:
        assert token not in HELPER_TEXT


def test_polkit_rule_is_exact_restart_only():
    assert validate_bounded_pilot_polkit_rule(POLKIT_RULE_TEXT)
    assert POLKIT_RULE_TEXT.count("polkit.Result.YES") == 1
    assert POLKIT_RULE_TEXT.count("polkit.Result.NOT_HANDLED") == 1
    assert 'action.lookup("unit") == "airiv-sentinel.service"' in POLKIT_RULE_TEXT
    assert 'action.lookup("verb") == "restart"' in POLKIT_RULE_TEXT
    assert 'subject.system_unit == "airiv-sentinel.service"' in POLKIT_RULE_TEXT
    assert "subject.no_new_privileges === true" in POLKIT_RULE_TEXT


@pytest.mark.parametrize(
    "field,value",
    [
        ("helper_id", "other"),
        ("unit", "other.service"),
        ("action", "STOP"),
        ("subject_system_unit", "other.service"),
        ("invocation_argv", (HELPER_PATH, "STOP", PILOT_UNIT)),
        ("systemctl_argv", (SYSTEMCTL, "--no-ask-password", "stop", PILOT_UNIT)),
    ],
)
def test_manifest_rejects_scope_substitution(field, value):
    manifest = canonical_bounded_pilot_helper_manifest()

    with pytest.raises(ValueError):
        replace(manifest, **{field: value})


def test_file_manifest_rejects_tampering():
    manifest = canonical_bounded_pilot_helper_manifest()

    with pytest.raises(ValueError, match="content hash mismatch"):
        BoundedPilotFileManifest(
            role="helper",
            destination=manifest.helper.destination,
            content=manifest.helper.content,
            content_sha256="0" * 64,
            owner_uid=0,
            owner_gid=0,
            mode=0o755,
        )

    with pytest.raises(ValueError, match="root-owned"):
        replace(manifest.helper, owner_uid=1000)

    with pytest.raises(ValueError, match="helper mode"):
        replace(manifest.helper, mode=0o644)

    with pytest.raises(ValueError, match="polkit rule mode"):
        replace(manifest.polkit_rule, mode=0o755)


def test_helper_readiness_requires_collision_free_exact_subject_and_content():
    ready = BoundedPilotHelperReadiness(
        helper_collision=False,
        polkit_collision=False,
        helper_content_matches=True,
        polkit_content_matches=True,
        helper_executable=True,
        polkit_rule_valid=True,
        subject_user="arivonto",
        subject_system_unit="airiv-sentinel.service",
        subject_no_new_privileges=True,
    )
    assert ready.activation_ready

    assert not replace(ready, helper_collision=True).activation_ready
    assert not replace(ready, polkit_collision=True).activation_ready
    assert not replace(ready, helper_content_matches=False).activation_ready
    assert not replace(ready, polkit_rule_valid=False).activation_ready
    assert not replace(ready, subject_user="root").activation_ready
    assert not replace(ready, subject_system_unit="user@1000.service").activation_ready
    assert not replace(ready, subject_no_new_privileges=False).activation_ready
