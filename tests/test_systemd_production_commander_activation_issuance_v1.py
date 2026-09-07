from pathlib import Path
from types import SimpleNamespace

import pytest

from sentinel.systemd_dispatch_evidence_binding import (
    TrustedSystemdDispatchEvidenceBinding,
)
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_approval_issuance import (
    SystemdProductionCommanderApprovalIssuer,
    TrustedSystemdProductionCommanderApproval,
)
from sentinel.systemd_production_commander_activation_issuance import (
    issue_systemd_production_activation_from_commander_continuation,
)
from sentinel.systemd_production_commander_incident_continuation import (
    SystemdProductionCommanderIncidentContinuation,
)
from sentinel.systemd_production_preparation import (
    PreparedSystemdProductionRemediation,
)
from sentinel.systemd_production_target_policy import (
    ACTION_RESTART,
)


def _exact_shell(cls, **values):
    obj = object.__new__(cls)

    for name, value in values.items():
        object.__setattr__(
            obj,
            name,
            value,
        )

    return obj


def _fixture(tmp_path):
    binding = _exact_shell(
        TrustedSystemdDispatchEvidenceBinding,
    )

    permit = SimpleNamespace(
        incident_id="incident-d817",
        component_id="systemd:d817-test.service",
        execution_id="execution-d817",
        effect_fingerprint="fingerprint-d817",
    )

    effect = SimpleNamespace(
        incident_id="incident-d817",
        component_id="systemd:d817-test.service",
        action=ACTION_RESTART,
        execution_id="execution-d817",
        effect_fingerprint="fingerprint-d817",
    )

    plan = SimpleNamespace(
        effect=effect,
        permit_binding=permit,
    )

    prepared = _exact_shell(
        PreparedSystemdProductionRemediation,
        binding=binding,
        plan=plan,
        prepared_at=110.0,
    )

    approval = _exact_shell(
        TrustedSystemdProductionCommanderApproval,
        approval_id="approval-d817",
        effect=permit,
        issued_at=100.0,
        expires_at=200.0,
    )

    continuation = (
        SystemdProductionCommanderIncidentContinuation(
            incident_id="incident-d817",
            component_id="systemd:d817-test.service",
            action=ACTION_RESTART,
            execution_id="execution-d817",
            approval_id="approval-d817",
            continued_at=120.0,
            approval_expires_at=200.0,
            binding=binding,
            prepared=prepared,
            approval=approval,
        )
    )

    issuer = SystemdProductionCommanderApprovalIssuer(
        tmp_path / "issuance"
    )

    return continuation, issuer


def _grant(activation_id="activation-d817", **changes):
    values = dict(
        activation_id=activation_id,
        approval_id="approval-d817",
        incident_id="incident-d817",
        component_id="systemd:d817-test.service",
        execution_id="execution-d817",
        effect_fingerprint="fingerprint-d817",
        issued_at=100.0,
        expires_at=200.0,
    )

    values.update(changes)

    return SystemdProductionActivationGrant(
        **values
    )


def test_delegates_exactly_once_to_d814(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    calls = []

    def fake_issue(
        self,
        *,
        approval,
        prepared,
        activation_id,
        now,
    ):
        calls.append(
            dict(
                self=self,
                approval=approval,
                prepared=prepared,
                activation_id=activation_id,
                now=now,
            )
        )

        return _grant(
            activation_id=activation_id
        )

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        fake_issue,
    )

    grant = (
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )
    )

    assert type(grant) is SystemdProductionActivationGrant
    assert len(calls) == 1

    call = calls[0]

    assert call["self"] is issuer
    assert call["approval"] is continuation.approval
    assert call["prepared"] is continuation.prepared
    assert call["activation_id"] == "activation-d817"
    assert call["now"] == 130.0


def test_continuation_type_is_exact(
    tmp_path,
):
    _, issuer = _fixture(
        tmp_path
    )

    with pytest.raises(
        TypeError,
        match="canonical Commander incident continuation",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=object(),
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )


def test_issuer_type_is_exact(
    tmp_path,
):
    continuation, _ = _fixture(
        tmp_path
    )

    with pytest.raises(
        TypeError,
        match="canonical Commander approval issuer",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=object(),
            activation_id="activation-d817",
            now=130.0,
        )


def test_time_reversal_fails_before_issuance(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    called = False

    def fake_issue(self, **kwargs):
        nonlocal called
        called = True
        return _grant()

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        fake_issue,
    )

    with pytest.raises(
        ValueError,
        match="continuation_time_reversal",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=119.0,
        )

    assert called is False


def test_expired_continuation_fails_before_issuance(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    called = False

    def fake_issue(self, **kwargs):
        nonlocal called
        called = True
        return _grant()

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        fake_issue,
    )

    with pytest.raises(
        ValueError,
        match="commander_continuation_expired",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=200.0,
        )

    assert called is False


def test_d816_fact_is_revalidated_before_issuance(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    object.__setattr__(
        continuation,
        "incident_id",
        "wrong-incident",
    )

    called = False

    def fake_issue(self, **kwargs):
        nonlocal called
        called = True
        return _grant()

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        fake_issue,
    )

    with pytest.raises(
        ValueError,
        match="incident_binding_mismatch",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )

    assert called is False


def test_noncanonical_grant_is_rejected(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        lambda self, **kwargs: object(),
    )

    with pytest.raises(
        TypeError,
        match="canonical activation grant",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )


@pytest.mark.parametrize(
    "changes,match",
    [
        (
            dict(
                approval_id="wrong-approval",
            ),
            "approval_id_continuity_mismatch",
        ),
        (
            dict(
                incident_id="wrong-incident",
            ),
            "activation_effect_continuity_mismatch",
        ),
        (
            dict(
                component_id="systemd:wrong.service",
            ),
            "activation_effect_continuity_mismatch",
        ),
        (
            dict(
                execution_id="wrong-execution",
            ),
            "activation_effect_continuity_mismatch",
        ),
        (
            dict(
                effect_fingerprint="wrong-fingerprint",
            ),
            "activation_effect_continuity_mismatch",
        ),
        (
            dict(
                issued_at=101.0,
            ),
            "activation_issued_at_continuity_mismatch",
        ),
        (
            dict(
                expires_at=201.0,
            ),
            "activation_expiry_continuity_mismatch",
        ),
    ],
)
def test_returned_grant_continuity_is_revalidated(
    tmp_path,
    monkeypatch,
    changes,
    match,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        lambda self, **kwargs: _grant(
            **changes
        ),
    )

    with pytest.raises(
        ValueError,
        match=match,
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )


def test_activation_id_return_continuity(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        lambda self, **kwargs: _grant(
            activation_id="wrong-activation"
        ),
    )

    with pytest.raises(
        ValueError,
        match="activation_id_continuity_mismatch",
    ):
        issue_systemd_production_activation_from_commander_continuation(
            continuation=continuation,
            issuer=issuer,
            activation_id="activation-d817",
            now=130.0,
        )


def test_boundary_does_not_mutate_continuation(
    tmp_path,
    monkeypatch,
):
    continuation, issuer = _fixture(
        tmp_path
    )

    before = (
        continuation.incident_id,
        continuation.component_id,
        continuation.action,
        continuation.execution_id,
        continuation.approval_id,
        continuation.continued_at,
        continuation.approval_expires_at,
    )

    monkeypatch.setattr(
        SystemdProductionCommanderApprovalIssuer,
        "issue",
        lambda self, **kwargs: _grant(
            activation_id=kwargs["activation_id"]
        ),
    )

    issue_systemd_production_activation_from_commander_continuation(
        continuation=continuation,
        issuer=issuer,
        activation_id="activation-d817",
        now=130.0,
    )

    after = (
        continuation.incident_id,
        continuation.component_id,
        continuation.action,
        continuation.execution_id,
        continuation.approval_id,
        continuation.continued_at,
        continuation.approval_expires_at,
    )

    assert after == before
