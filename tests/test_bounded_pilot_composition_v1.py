"""Bounded pilot composition regression."""

from dataclasses import replace

import pytest

from sentinel.bounded_pilot_bootstrap_executor import (
    BoundedPilotBootstrapResult,
)
from sentinel.bounded_pilot_composition import (
    compose_bounded_pilot_readiness,
)
from sentinel.bounded_pilot_helper_manifest import (
    BoundedPilotHelperReadiness,
)
from sentinel.bounded_pilot_readiness import (
    BoundedPilotReadinessState,
    BoundedPilotRuntimeFacts,
    BoundedPilotVerificationFacts,
)


def helper_ready(**changes):
    values = dict(
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
    values.update(changes)
    return BoundedPilotHelperReadiness(**values)


def bootstrap(status="SUCCEEDED"):
    return BoundedPilotBootstrapResult(
        status=status,
        manifest_fingerprint="a" * 64,
        events=("test",),
        error=None if status == "SUCCEEDED" else "blocked",
        rollback_errors=(),
    )


def verification(**changes):
    values = dict(
        pid_check=True,
        active_state_check=True,
        runtime_identity_check=True,
        journal_continuity_check=True,
        evidence_path_validated=True,
    )
    values.update(changes)
    return BoundedPilotVerificationFacts(**values)


def runtime(**changes):
    values = dict(
        now=1000.0,
        activated_at=999.0,
        unknown_retry_count=0,
        active_effects=0,
    )
    values.update(changes)
    return BoundedPilotRuntimeFacts(**values)


def compose(**changes):
    values = dict(
        helper_readiness=helper_ready(),
        bootstrap_result=bootstrap(),
        verification=verification(),
        runtime=runtime(),
    )
    values.update(changes)
    return compose_bounded_pilot_readiness(**values)


def test_ready_when_all_composed_facts_are_ready():
    result = compose()

    assert result.ready is True
    assert result.state is BoundedPilotReadinessState.READY
    assert result.reasons == ("bounded_pilot_ready",)


def test_bootstrap_failure_blocks_even_if_helper_shape_is_ready():
    result = compose(bootstrap_result=bootstrap("ROLLED_BACK"))

    assert result.ready is False
    assert "helper_not_installed" in result.reasons
    assert "bootstrap_not_succeeded" in result.reasons


def test_helper_readiness_gap_blocks_activation():
    result = compose(
        helper_readiness=helper_ready(subject_system_unit="user@1000.service")
    )

    assert result.ready is False
    assert "helper_readiness_not_ready" in result.reasons


def test_verification_gap_remains_fail_closed():
    result = compose(
        verification=verification(journal_continuity_check=False)
    )

    assert result.ready is False
    assert "journal_continuity_verification_missing" in result.reasons


def test_runtime_unknown_retry_still_blocks():
    result = compose(runtime=runtime(unknown_retry_count=1))

    assert result.ready is False
    assert "unknown_retry_budget_exceeded" in result.reasons


def test_wrong_types_rejected():
    with pytest.raises(TypeError):
        compose(helper_readiness=object())

    with pytest.raises(TypeError):
        compose(bootstrap_result=object())


def test_composition_is_immutable_projection():
    original = helper_ready()
    changed = replace(original, helper_content_matches=False)

    assert original.activation_ready is True
    assert changed.activation_ready is False
    assert compose(helper_readiness=changed).ready is False
