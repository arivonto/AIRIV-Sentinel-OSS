from __future__ import annotations

import pytest

from sentinel.bound_effect_contract import (
    BoundRemediationEffectContract,
    bound_effect_policy_run_id,
    validate_bound_effect_contract,
)
from sentinel.remediation_policy import (
    RemediationPolicy,
)
from sentinel.resource_bound_remediation import (
    GenericBoundRemediationEffect,
)
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity,
    SystemdUnitIdentity,
)


ACTION = "systemd_restart"


def make_generic_effect(
    *,
    run_id="RUN-D3",
):
    manager = SystemdManagerIdentity(
        boot_id=(
            "11111111-2222-3333-4444-555555555555"
        ),
        manager_pid=1,
        manager_start_ticks=123456,
    )

    target = SystemdUnitIdentity(
        manager=manager,

        unit_name=(
            "airiv-sentinel.service"
        ),

        fragment_path=(
            "/etc/systemd/system/"
            "airiv-sentinel.service"
        ),

        fragment_sha256="a" * 64,

        fragment_device=1,
        fragment_inode=2,
        fragment_uid=0,
        fragment_gid=0,
    )

    return GenericBoundRemediationEffect(
        run_id=run_id,

        incident_id="INC-D3",

        component_id=(
            target.component_id
        ),

        resource_kind=(
            "systemd.service"
        ),

        target=target,

        scope_fingerprint="b" * 64,

        action=ACTION,

        argv=(
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            "airiv-sentinel.service",
        ),

        execution_id="EXEC-D3",
        permit_id="PERMIT-D3",
    )


def test_generic_policy_run_id_is_effect_run_id():
    effect = make_generic_effect()

    assert (
        effect.policy_run_id
        == "RUN-D3"
    )

    assert (
        bound_effect_policy_run_id(
            effect
        )
        == "RUN-D3"
    )


def test_resource_identity_does_not_gain_remediation_run_id():
    effect = make_generic_effect()

    assert not hasattr(
        effect.target,
        "run_id",
    )

    assert (
        effect.target.component_id
        == "systemd:airiv-sentinel.service"
    )


def test_policy_indexes_generic_effect_by_contract_run_id():
    effect = make_generic_effect(
        run_id="RUN-GENERIC-POLICY"
    )

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    policy.configure_bound_effect(
        effect
    )

    assert (
        "RUN-GENERIC-POLICY"
        in policy.list_bound_runs()
    )


def test_policy_evaluates_generic_effect_by_same_run_id():
    effect = make_generic_effect(
        run_id="RUN-GENERIC-EVAL"
    )

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    policy.configure_bound_effect(
        effect
    )

    decision = policy.evaluate_bound(
        incident_state="INVESTIGATING",
        effect=effect,
    )

    assert decision is not None


def test_different_generic_run_does_not_alias():
    first = make_generic_effect(
        run_id="RUN-A"
    )

    second = make_generic_effect(
        run_id="RUN-B"
    )

    policy = RemediationPolicy(
        allowed_actions={
            ACTION
        }
    )

    policy.configure_bound_effect(
        first
    )

    assert policy.list_bound_runs() == (
        "RUN-A",
    )

    # Policy engines fail closed by returning a DENY decision.
    # An unconfigured run is not an exceptional runtime condition.
    decision = policy.evaluate_bound(
        incident_state="INVESTIGATING",
        effect=second,
    )

    assert decision.authorized is False

    # RUN-B must never become registered or alias RUN-A.
    assert policy.list_bound_runs() == (
        "RUN-A",
    )


def test_nominal_member_without_policy_run_id_fails_closed():
    class BrokenEffect(
        BoundRemediationEffectContract
    ):
        pass

    with pytest.raises(
        TypeError,
        match="policy_run_id",
    ):
        validate_bound_effect_contract(
            BrokenEffect()
        )


def test_arbitrary_object_still_rejected():
    class Fake:
        policy_run_id = "RUN-X"
        action = ACTION

    with pytest.raises(
        TypeError,
        match="effect must be a BoundRemediationEffect",
    ):
        validate_bound_effect_contract(
            Fake()
        )
