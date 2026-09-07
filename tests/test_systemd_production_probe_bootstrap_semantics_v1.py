from pathlib import Path

from sentinel.systemd_production_probe_design import (
    PROBE_POLKIT_RULE_TEXT,
)


def contract():
    return (
        Path(
            "contracts/"
            "SYSTEMD_PRODUCTION_REMEDIATION_PROBE_BOOTSTRAP_CONTRACT.md"
        )
        .read_text(
            encoding="utf-8"
        )
    )


def test_contract_reuses_d7d_authorization_evidence_boundary():
    text = contract()

    assert (
        "D7D.1 / D7D.2"
        in text
    )

    assert (
        "`pkcheck --process PID,START_TIME,UID` is synthetic evidence."
        in text
    )


def test_synthetic_pkcheck_cannot_claim_strong_subject_predicates():
    text = contract()

    assert (
        "It MUST NOT be used by D8.12C to claim proof of:"
        in text
    )

    assert "`subject.system_unit`" in text
    assert "`subject.no_new_privileges`" in text
    assert "real systemd D-Bus authorization" in text


def test_real_authorization_is_separate_commander_gated_effect():
    text = contract()

    assert (
        "future real D-Bus authorization/restart validation requires a fresh"
        in text
    )

    assert (
        "Commander approval"
        in text
    )


def test_probe_rule_retains_exact_strong_predicates():
    required = (
        'action.id == "org.freedesktop.systemd1.manage-units"',
        'action.lookup("unit") == '
        '"airiv-sentinel-production-remediation-probe.service"',
        'action.lookup("verb") == "restart"',
        'subject.user == "arivonto"',
        'subject.system_unit == "airiv-sentinel.service"',
        'subject.no_new_privileges === true',
        "polkit.Result.NOT_HANDLED",
    )

    for token in required:
        assert token in PROBE_POLKIT_RULE_TEXT


def test_bootstrap_contract_keeps_runtime_closed():
    text = contract()

    assert (
        "Production target allowlist remains empty."
        in text
    )

    assert (
        "All production runtime layers remain disabled"
        in text
    )
