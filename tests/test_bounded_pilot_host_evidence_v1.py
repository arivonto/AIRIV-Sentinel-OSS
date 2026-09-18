"""Bounded pilot host evidence projection regression."""

import ast
import inspect

import pytest

from sentinel import bounded_pilot_host_evidence as module
from sentinel.bounded_pilot_bootstrap_executor import (
    BoundedPilotBootstrapResult,
)
from sentinel.bounded_pilot_composition import (
    compose_bounded_pilot_readiness,
)
from sentinel.bounded_pilot_helper_manifest import (
    BoundedPilotHelperReadiness,
)
from sentinel.bounded_pilot_host_evidence import (
    BoundedPilotHostEvidence,
    project_bounded_pilot_host_evidence,
)
from sentinel.bounded_pilot_readiness import (
    BoundedPilotRuntimeFacts,
)


def evidence(**changes):
    values = dict(
        unit="airiv-sentinel.service",
        active_state="active",
        sub_state="running",
        main_pid=1234,
        runtime_identity="constitution-v1.1:e8d9648",
        expected_runtime_identity="constitution-v1.1:e8d9648",
        journal_unit="airiv-sentinel.service",
        journal_boot_id="12345678-1234-1234-1234-123456789abc",
        journal_after_activation=True,
        evidence_path_validated=True,
        observed_at=2000.0,
        activation_observed_at=1990.0,
    )
    values.update(changes)
    return BoundedPilotHostEvidence(**values)


def helper_ready():
    return BoundedPilotHelperReadiness(
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


def bootstrap_succeeded():
    return BoundedPilotBootstrapResult(
        status="SUCCEEDED",
        manifest_fingerprint="a" * 64,
        events=("test",),
        error=None,
        rollback_errors=(),
    )


def runtime_ready():
    return BoundedPilotRuntimeFacts(
        now=2000.0,
        activated_at=1990.0,
        unknown_retry_count=0,
        active_effects=0,
    )


def test_exact_host_evidence_projects_to_verification_facts():
    projection = project_bounded_pilot_host_evidence(evidence())

    assert projection.verified is True
    assert projection.reasons == ("bounded_pilot_host_evidence_verified",)
    assert projection.verification.pid_check is True
    assert projection.verification.active_state_check is True
    assert projection.verification.runtime_identity_check is True
    assert projection.verification.journal_continuity_check is True
    assert projection.verification.evidence_path_validated is True


@pytest.mark.parametrize(
    "changes,reason,field",
    [
        (
            {"unit": "other.service"},
            "host_unit_mismatch",
            "pid_check",
        ),
        (
            {"main_pid": 0},
            "host_pid_missing",
            "pid_check",
        ),
        (
            {"active_state": "failed"},
            "host_not_active_running",
            "active_state_check",
        ),
        (
            {"runtime_identity": "stale"},
            "host_runtime_identity_mismatch",
            "runtime_identity_check",
        ),
        (
            {"journal_unit": "other.service"},
            "journal_unit_mismatch",
            "journal_continuity_check",
        ),
        (
            {"journal_boot_id": "missing"},
            "journal_boot_id_missing",
            "journal_continuity_check",
        ),
        (
            {"journal_after_activation": False},
            "journal_after_activation_missing",
            "journal_continuity_check",
        ),
        (
            {"observed_at": 1980.0},
            "host_evidence_precedes_activation",
            "journal_continuity_check",
        ),
        (
            {"evidence_path_validated": False},
            "host_evidence_path_not_validated",
            "evidence_path_validated",
        ),
    ],
)
def test_incomplete_or_mismatched_host_evidence_fails_closed(
    changes,
    reason,
    field,
):
    if changes == {"journal_boot_id": "missing"}:
        changes = {"journal_boot_id": ""}
        with pytest.raises(ValueError):
            evidence(**changes)
        return

    projection = project_bounded_pilot_host_evidence(evidence(**changes))

    assert projection.verified is False
    assert reason in projection.reasons
    assert getattr(projection.verification, field) is False


def test_projected_host_evidence_feeds_existing_activation_gate():
    projection = project_bounded_pilot_host_evidence(evidence())

    result = compose_bounded_pilot_readiness(
        helper_readiness=helper_ready(),
        bootstrap_result=bootstrap_succeeded(),
        verification=projection.verification,
        runtime=runtime_ready(),
    )

    assert result.ready is True


def test_projected_host_gap_blocks_existing_activation_gate():
    projection = project_bounded_pilot_host_evidence(
        evidence(runtime_identity="stale")
    )

    result = compose_bounded_pilot_readiness(
        helper_readiness=helper_ready(),
        bootstrap_result=bootstrap_succeeded(),
        verification=projection.verification,
        runtime=runtime_ready(),
    )

    assert result.ready is False
    assert "runtime_identity_verification_missing" in result.reasons


def test_invalid_host_evidence_shape_is_rejected():
    with pytest.raises(ValueError, match="main_pid must be exact integer"):
        evidence(main_pid=True)

    with pytest.raises(ValueError, match="observed_at"):
        evidence(observed_at=float("nan"))

    with pytest.raises(TypeError):
        project_bounded_pilot_host_evidence(object())


def test_host_evidence_projection_has_no_effect_authority():
    tree = ast.parse(inspect.getsource(module))
    forbidden = {
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "restart",
        "execute_argv",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "resolve",
    }
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not names & forbidden
