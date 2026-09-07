from __future__ import annotations

import pytest

from sentinel.bound_effect_contract import (
    BoundRemediationEffectContract,
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


def make_generic_effect():
    manager = SystemdManagerIdentity(
        boot_id=(
            "11111111-2222-3333-4444-555555555555"
        ),
        manager_pid=1,
        manager_start_ticks=123,
    )

    target = SystemdUnitIdentity(
        manager=manager,
        unit_name="airiv-sentinel.service",
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
        run_id="RUN-CONTRACT",
        incident_id="INC-CONTRACT",
        component_id=target.component_id,
        resource_kind="systemd.service",
        target=target,
        scope_fingerprint="b" * 64,
        action="systemd_restart",
        argv=(
            "/usr/bin/systemctl",
            "--no-ask-password",
            "restart",
            "airiv-sentinel.service",
        ),
        execution_id="EXEC-CONTRACT",
        permit_id="PERMIT-CONTRACT",
    )


def test_generic_effect_explicitly_satisfies_nominal_contract():
    effect = make_generic_effect()

    assert isinstance(
        effect,
        BoundRemediationEffectContract,
    )

    validate_bound_effect_contract(
        effect
    )


def test_arbitrary_duck_typed_effect_is_rejected():
    class FakeEffect:
        run_id = "RUN"
        incident_id = "INC"
        component_id = "systemd:x.service"
        resource_kind = "systemd.service"
        target_fingerprint = "a" * 64
        scope_fingerprint = "b" * 64
        action = "systemd_restart"
        argv = (
            "/usr/bin/systemctl",
            "restart",
            "x.service",
        )
        execution_id = "EXEC"
        permit_id = "PERMIT"
        fingerprint = "c" * 64

    with pytest.raises(
        TypeError,
        match="effect must be a BoundRemediationEffect",
    ):
        validate_bound_effect_contract(
            FakeEffect()
        )


def test_policy_rejects_non_nominal_effect_even_with_matching_fields():
    class FakeEffect:
        run_id = "RUN"
        action = "systemd_restart"

    policy = RemediationPolicy(
        allowed_actions={
            "systemd_restart"
        }
    )

    with pytest.raises(
        TypeError,
        match="effect must be a BoundRemediationEffect",
    ):
        policy.configure_bound_effect(
            FakeEffect()
        )
