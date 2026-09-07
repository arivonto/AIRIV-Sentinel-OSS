from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import json

import pytest

from sentinel.live_remediation_safety import (
    BoundRemediationAuthorization,
    BoundRemediationEffect,
    LiveRunPermitClaim,
    TmuxTargetIdentity,
)
from sentinel.remediation_execution_identity import (
    RemediationExecutionIdentityJournal,
)
from sentinel.remediation_policy import RemediationPolicy


ACTION = "controlled_tmux_effect"


def target(
    *,
    run_id: str = "run-213c1b",
    pane_id: str = "%7",
    session_id: str = "$42",
    session_name: str = "airiv-213c1b",
    window_id: str = "@9",
    generation: str | None = "uid=1000;pid=1234;start=5678",
):
    return TmuxTargetIdentity(
        run_id=run_id,
        server_socket="/tmp/airiv-213c1b.sock",
        server_generation=generation,
        session_id=session_id,
        session_name=session_name,
        window_id=window_id,
        pane_id=pane_id,
    )


def effect(
    *,
    target_identity=None,
    incident_id="INC-213C1B",
    action=ACTION,
    execution_id="EXEC-213C1B",
    permit_id="PERMIT-213C1B",
    argv=None,
):
    t = target_identity or target()

    return BoundRemediationEffect(
        incident_id=incident_id,
        component_id=t.pane_id,
        action=action,
        argv=argv
        or (
            "tmux",
            "-S",
            t.server_socket,
            "display-message",
            "-p",
            "-t",
            t.pane_id,
            "#{pane_id}",
        ),
        target=t,
        execution_id=execution_id,
        permit_id=permit_id,
    )


def configured_policy(bound_effect):
    policy = RemediationPolicy()
    policy.allowed_actions = {bound_effect.action}
    policy.configure_bound_effect(bound_effect)
    return policy


def test_bound_policy_requires_exact_effect():
    original = effect()
    policy = configured_policy(original)

    decision = policy.evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    assert isinstance(
        decision,
        BoundRemediationAuthorization,
    )
    assert decision.authorized
    assert decision.decision == "ALLOW"
    assert decision.matches(original)
    assert decision.effect_fingerprint == original.fingerprint
    assert (
        decision.target_fingerprint
        == original.target.fingerprint
    )


@pytest.mark.parametrize(
    "mutated",
    [
        effect(
            argv=(
                "tmux",
                "-S",
                "/tmp/airiv-213c1b.sock",
                "display-message",
                "-p",
                "-t",
                "%7",
                "#{session_name}",
            )
        ),
        effect(
            incident_id="INC-TAMPERED",
        ),
        effect(
            execution_id="EXEC-TAMPERED",
        ),
        effect(
            permit_id="PERMIT-TAMPERED",
        ),
        effect(
            target_identity=target(
                session_id="$99",
            )
        ),
        effect(
            target_identity=target(
                window_id="@77",
            )
        ),
    ],
)
def test_bound_policy_rejects_any_binding_tamper(mutated):
    original = effect()
    policy = configured_policy(original)

    decision = policy.evaluate_bound(
        incident_state="OPEN",
        effect=mutated,
    )

    assert not decision.authorized
    assert decision.decision == "DENY"
    assert decision.reason == "bound_effect_mismatch"


def test_bound_policy_denies_unconfigured_run():
    original = effect()
    policy = RemediationPolicy()
    policy.allowed_actions = {original.action}

    decision = policy.evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    assert not decision.authorized
    assert decision.reason == "bound_run_not_configured"


def test_bound_policy_denies_weak_target_identity():
    weak = effect(
        target_identity=target(
            generation=None,
        )
    )

    policy = RemediationPolicy()
    policy.allowed_actions = {weak.action}
    policy.configure_bound_effect(weak)

    decision = policy.evaluate_bound(
        incident_state="OPEN",
        effect=weak,
    )

    assert not decision.authorized
    assert decision.reason == "target_identity_not_live_eligible"


def test_bound_policy_cannot_bypass_legacy_deny():
    original = effect()

    policy = RemediationPolicy()
    policy.allowed_actions = set()

    # Configuration itself must not bootstrap authorization.
    with pytest.raises(ValueError):
        policy.configure_bound_effect(original)


def test_bound_policy_configuration_is_instance_local():
    original = effect()
    configured = configured_policy(original)

    fresh = RemediationPolicy()

    assert configured.list_bound_runs() == (
        original.target.run_id,
    )
    assert fresh.list_bound_runs() == ()
    assert fresh.allowed_actions == set()


def test_bound_authorization_is_immutable():
    original = effect()
    decision = configured_policy(
        original
    ).evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    with pytest.raises(FrozenInstanceError):
        decision.reason = "tampered"


def test_first_one_run_permit_claim_is_durable(tmp_path):
    original = effect()
    authorization = configured_policy(
        original
    ).evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    claim = journal.claim_live_run_permit(
        effect=original,
        authorization=authorization,
    )

    assert isinstance(claim, LiveRunPermitClaim)
    assert not claim.replayed
    assert claim.record.run_id == original.target.run_id
    assert claim.record.execution_id == original.execution_id
    assert (
        claim.record.effect_fingerprint
        == original.fingerprint
    )
    assert (
        claim.record.authorization_fingerprint
        == authorization.fingerprint
    )

    persisted = journal.get_live_run_permit(
        original.target.run_id
    )

    assert persisted == claim.record

    files = list(
        (
            tmp_path
            / "IDENTITY"
            / "_live_run_permits"
        ).glob("*.json")
    )

    assert len(files) == 1

    payload = json.loads(files[0].read_text())

    assert payload == claim.record.canonical_dict()


def test_exact_same_run_replay_never_creates_second_permit(tmp_path):
    original = effect()
    authorization = configured_policy(
        original
    ).evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    first = journal.claim_live_run_permit(
        effect=original,
        authorization=authorization,
    )

    replay = journal.claim_live_run_permit(
        effect=original,
        authorization=authorization,
    )

    assert not first.replayed
    assert replay.replayed
    assert replay.record == first.record

    assert len(
        list(
            (
                tmp_path
                / "IDENTITY"
                / "_live_run_permits"
            ).glob("*.json")
        )
    ) == 1


@pytest.mark.parametrize(
    "mutated",
    [
        effect(execution_id="EXEC-SECOND"),
        effect(permit_id="PERMIT-SECOND"),
        effect(incident_id="INC-SECOND"),
        effect(
            target_identity=target(
                session_id="$SECOND",
            )
        ),
        effect(
            argv=(
                "tmux",
                "-S",
                "/tmp/airiv-213c1b.sock",
                "display-message",
                "-p",
                "-t",
                "%7",
                "#{session_name}",
            )
        ),
    ],
)
def test_same_run_rejects_distinct_identity_or_effect(
    tmp_path,
    mutated,
):
    original = effect()

    policy = configured_policy(original)

    authorization = policy.evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    journal.claim_live_run_permit(
        effect=original,
        authorization=authorization,
    )

    # Create a matching authorization for the tampered effect so this test
    # proves the durable one-run journal independently rejects the second
    # logical execution under the same run_id.
    second_policy = configured_policy(mutated)

    second_authorization = second_policy.evaluate_bound(
        incident_state="OPEN",
        effect=mutated,
    )

    assert second_authorization.authorized

    with pytest.raises(
        RuntimeError,
        match="live_run_permit_conflict",
    ):
        journal.claim_live_run_permit(
            effect=mutated,
            authorization=second_authorization,
        )


def test_cross_target_replay_under_same_run_is_rejected(tmp_path):
    original = effect()

    other_target = target(
        pane_id="%99",
        session_id="$99",
        window_id="@99",
    )

    other = effect(
        target_identity=other_target,
        execution_id="EXEC-OTHER",
        permit_id="PERMIT-OTHER",
    )

    first_policy = configured_policy(original)
    second_policy = configured_policy(other)

    first_auth = first_policy.evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    second_auth = second_policy.evaluate_bound(
        incident_state="OPEN",
        effect=other,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    journal.claim_live_run_permit(
        effect=original,
        authorization=first_auth,
    )

    with pytest.raises(
        RuntimeError,
        match="live_run_permit_conflict",
    ):
        journal.claim_live_run_permit(
            effect=other,
            authorization=second_auth,
        )


def test_denied_authorization_never_claims_permit(tmp_path):
    original = effect()

    policy = RemediationPolicy()
    policy.allowed_actions = {original.action}

    denied = policy.evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    assert not denied.authorized

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    with pytest.raises(PermissionError):
        journal.claim_live_run_permit(
            effect=original,
            authorization=denied,
        )

    assert (
        journal.get_live_run_permit(
            original.target.run_id
        )
        is None
    )


def test_authorization_from_different_effect_is_rejected(tmp_path):
    original = effect()
    changed = effect(
        execution_id="EXEC-DIFFERENT",
    )

    authorization = configured_policy(
        original
    ).evaluate_bound(
        incident_state="OPEN",
        effect=original,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    with pytest.raises(
        PermissionError,
        match="authorization_effect_binding_mismatch",
    ):
        journal.claim_live_run_permit(
            effect=changed,
            authorization=authorization,
        )


def test_concurrent_distinct_execution_ids_same_run_only_one_claims(
    tmp_path,
):
    first = effect(
        execution_id="EXEC-A",
        permit_id="PERMIT-A",
    )

    second = effect(
        execution_id="EXEC-B",
        permit_id="PERMIT-B",
    )

    first_auth = configured_policy(
        first
    ).evaluate_bound(
        incident_state="OPEN",
        effect=first,
    )

    second_auth = configured_policy(
        second
    ).evaluate_bound(
        incident_state="OPEN",
        effect=second,
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    def claim(pair):
        item, authorization = pair

        try:
            result = journal.claim_live_run_permit(
                effect=item,
                authorization=authorization,
            )
            return (
                "CLAIMED",
                result.record.execution_id,
            )

        except RuntimeError as exc:
            return (
                str(exc),
                item.execution_id,
            )

    with ThreadPoolExecutor(
        max_workers=2
    ) as pool:
        results = list(
            pool.map(
                claim,
                [
                    (first, first_auth),
                    (second, second_auth),
                ],
            )
        )

    statuses = sorted(
        result[0]
        for result in results
    )

    assert statuses == [
        "CLAIMED",
        "live_run_permit_conflict",
    ]

    persisted = journal.get_live_run_permit(
        first.target.run_id
    )

    assert persisted is not None
    assert persisted.execution_id in {
        "EXEC-A",
        "EXEC-B",
    }


def test_different_runs_may_each_claim_once(tmp_path):
    first = effect(
        target_identity=target(
            run_id="run-A",
        ),
        execution_id="EXEC-A",
        permit_id="PERMIT-A",
    )

    second = effect(
        target_identity=target(
            run_id="run-B",
        ),
        execution_id="EXEC-B",
        permit_id="PERMIT-B",
    )

    journal = RemediationExecutionIdentityJournal(
        tmp_path / "IDENTITY"
    )

    for item in (first, second):
        auth = configured_policy(
            item
        ).evaluate_bound(
            incident_state="OPEN",
            effect=item,
        )

        claim = journal.claim_live_run_permit(
            effect=item,
            authorization=auth,
        )

        assert not claim.replayed

    assert journal.get_live_run_permit("run-A") is not None
    assert journal.get_live_run_permit("run-B") is not None
