import ast
import dataclasses
import inspect
import json
import os
from pathlib import Path
import textwrap

import pytest

import sentinel.systemd_production_activation_consumption as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_activation_consumption import (
    SystemdProductionActivationConsumptionRecord,
    SystemdProductionActivationConsumptionStore,
)


def grant(
    **changes,
):
    values = {
        "activation_id":
            "ACT-D810B-001",

        "approval_id":
            "APPROVAL-D810B-001",

        "incident_id":
            "INC-D810B",

        "component_id":
            "systemd:example.service",

        "execution_id":
            "EXEC-D810B",

        "effect_fingerprint":
            "f" * 64,

        "issued_at":
            100.0,

        "expires_at":
            160.0,
    }

    values.update(
        changes
    )

    return SystemdProductionActivationGrant(
        **values
    )


def consume(
    store,
    value=None,
    *,
    now=120.0,
):
    value = (
        grant()
        if value is None
        else value
    )

    return store.consume(
        grant=value,
        now=now,
        incident_id=value.incident_id,
        component_id=value.component_id,
        execution_id=value.execution_id,
        effect_fingerprint=(
            value.effect_fingerprint
        ),
    )


def test_default_store_is_empty_and_absolute():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    assert store.root.is_absolute()
    assert store.records() == ()


def test_successful_consume_is_durable_and_private():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    value = grant()

    record = consume(
        store,
        value,
    )

    assert (
        record.activation_id
        == value.activation_id
    )

    assert (
        record.grant_fingerprint
        == value.fingerprint
    )

    assert record.consumed_at == 120.0

    assert (
        store.records()
        == (
            record,
        )
    )

    assert (
        SystemdProductionActivationConsumptionStore()
        .records()
        == (
            record,
        )
    )

    assert (
        store.root.stat().st_mode
        & 0o777
        == 0o700
    )

    path = (
        store.root
        / record.filename
    )

    assert (
        path.stat().st_mode
        & 0o777
        == 0o600
    )


def test_duplicate_same_grant_never_overwrites():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    first = consume(
        store
    )

    path = (
        store.root
        / first.filename
    )

    original = path.read_bytes()

    with pytest.raises(
        ValueError,
        match="activation_already_consumed",
    ):
        consume(
            store
        )

    assert path.read_bytes() == original
    assert store.records() == (first,)


def test_same_activation_id_with_modified_grant_is_still_consumed():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    first = consume(
        store
    )

    changed = grant(
        approval_id="APPROVAL-D810B-OTHER",
        incident_id="INC-D810B-OTHER",
        component_id="systemd:other.service",
        execution_id="EXEC-D810B-OTHER",
        effect_fingerprint="e" * 64,
    )

    with pytest.raises(
        ValueError,
        match="activation_already_consumed",
    ):
        consume(
            store,
            changed,
        )

    assert store.records() == (first,)


def test_expired_grant_is_not_consumed():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    with pytest.raises(
        ValueError,
        match="activation_not_active",
    ):
        consume(
            store,
            now=160.0,
        )

    assert store.records() == ()


def test_effect_mismatch_is_not_consumed():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    value = grant()

    with pytest.raises(
        ValueError,
        match="activation_effect_binding_mismatch",
    ):
        store.consume(
            grant=value,
            now=120.0,
            incident_id="INC-OTHER",
            component_id=value.component_id,
            execution_id=value.execution_id,
            effect_fingerprint=(
                value.effect_fingerprint
            ),
        )

    assert store.records() == ()


def test_record_filename_is_activation_id_keyed():
    value = grant()

    first = (
        SystemdProductionActivationConsumptionRecord
        .from_grant(
            value,
            120.0,
        )
    )

    second_value = grant(
        approval_id="APPROVAL-D810B-OTHER",
        incident_id="INC-OTHER",
        execution_id="EXEC-OTHER",
        effect_fingerprint="e" * 64,
    )

    second = (
        SystemdProductionActivationConsumptionRecord
        .from_grant(
            second_value,
            121.0,
        )
    )

    assert (
        first.filename
        == second.filename
    )

    assert (
        first.grant_fingerprint
        != second.grant_fingerprint
    )


def test_consumed_query_is_durable():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    assert (
        store.consumed(
            "ACT-D810B-001"
        )
        is False
    )

    consume(
        store
    )

    assert (
        SystemdProductionActivationConsumptionStore()
        .consumed(
            "ACT-D810B-001"
        )
        is True
    )


def test_corrupt_published_record_blocks_future_consumption():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    first = consume(
        store
    )

    path = (
        store.root
        / first.filename
    )

    path.write_text(
        "{",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        store.records()

    another = grant(
        activation_id="ACT-D810B-002",
        execution_id="EXEC-D810B-002",
    )

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        consume(
            store,
            another,
        )


def test_noncanonical_payload_blocks_state():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    record = consume(
        store
    )

    path = (
        store.root
        / record.filename
    )

    payload = record.to_dict()

    path.write_text(
        json.dumps(
            payload,
            sort_keys=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        store.records()


def test_wrong_filename_blocks_state():
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    record = consume(
        store
    )

    path = (
        store.root
        / record.filename
    )

    wrong = (
        store.root
        / (
            "0" * 64
            + ".json"
        )
    )

    path.rename(
        wrong
    )

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        store.records()


def test_partial_reservation_is_retained_and_fails_closed(
    monkeypatch,
):
    store = (
        SystemdProductionActivationConsumptionStore()
    )

    store.root.mkdir(
        mode=0o700,
        parents=True,
    )

    real_fsync = module.os.fsync
    calls = 0

    def fail_first_fsync(
        fd,
    ):
        nonlocal calls

        calls += 1

        if calls == 1:
            raise OSError(
                "simulated reservation fsync failure"
            )

        return real_fsync(
            fd
        )

    monkeypatch.setattr(
        module.os,
        "fsync",
        fail_first_fsync,
    )

    value = grant()

    with pytest.raises(
        OSError,
        match="simulated reservation fsync failure",
    ):
        consume(
            store,
            value,
        )

    monkeypatch.setattr(
        module.os,
        "fsync",
        real_fsync,
    )

    expected = (
        store.root
        / (
            __import__(
                "hashlib"
            )
            .sha256(
                value.activation_id.encode(
                    "utf-8"
                )
            )
            .hexdigest()
            + ".json"
        )
    )

    assert expected.exists()

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        store.records()

    with pytest.raises(
        ValueError,
        match="malformed durable activation consumption",
    ):
        consume(
            store,
            value,
        )


def test_file_symlink_is_never_followed(
    tmp_path,
):
    root = (
        tmp_path
        / "activation"
    )

    root.mkdir(
        mode=0o700
    )

    value = grant()

    record = (
        SystemdProductionActivationConsumptionRecord
        .from_grant(
            value,
            120.0,
        )
    )

    target = (
        tmp_path
        / "target"
    )

    target.write_text(
        "{}",
        encoding="utf-8",
    )

    (
        root
        / record.filename
    ).symlink_to(
        target
    )

    store = (
        SystemdProductionActivationConsumptionStore(
            root
        )
    )

    with pytest.raises(
        (
            OSError,
            ValueError,
        )
    ):
        store.records()


def test_root_symlink_is_rejected(
    tmp_path,
):
    target = (
        tmp_path
        / "target"
    )

    target.mkdir(
        mode=0o700
    )

    root = (
        tmp_path
        / "activation"
    )

    root.symlink_to(
        target,
        target_is_directory=True,
    )

    store = (
        SystemdProductionActivationConsumptionStore(
            root
        )
    )

    with pytest.raises(
        (
            OSError,
            ValueError,
        )
    ):
        consume(
            store
        )


def test_record_roundtrip_is_exact():
    record = (
        SystemdProductionActivationConsumptionRecord
        .from_grant(
            grant(),
            120.0,
        )
    )

    restored = (
        SystemdProductionActivationConsumptionRecord
        .from_dict(
            record.to_dict()
        )
    )

    assert restored == record


@pytest.mark.parametrize(
    "payload",
    (
        {},
        {
            "activation_id":
                "bad id",
        },
        {
            "activation_id":
                "ACT-D810B-001",

            "approval_id":
                "APPROVAL",

            "incident_id":
                "INC",

            "component_id":
                "systemd:example.service",

            "execution_id":
                "EXEC",

            "effect_fingerprint":
                "f" * 64,

            "grant_fingerprint":
                "not-a-fingerprint",

            "consumed_at":
                120.0,
        },
    ),
)
def test_malformed_record_fails_closed(
    payload,
):
    with pytest.raises(
        ValueError,
        match="malformed activation consumption record",
    ):
        (
            SystemdProductionActivationConsumptionRecord
            .from_dict(
                payload
            )
        )


def test_runtime_does_not_own_consumption_store():
    runtime = SentinelRuntime()

    assert not hasattr(
        runtime,
        "systemd_production_activation_consumption"
    )

    assert (
        runtime
        .systemd_production_runtime_delegation_bridge
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_runtime_invocation
        .enabled
        is False
    )

    assert (
        runtime
        .systemd_production_execution_dispatch_gate
        .enabled
        is False
    )

    assert (
        runtime.policy
        .list_systemd_production_targets()
        == ()
    )


def test_runtime_run_once_has_no_consumption_path():
    source = inspect.getsource(
        SentinelRuntime.run_once
    )

    assert (
        "activation_consumption"
        not in source
    )

    assert (
        ".consume("
        not in source
    )


def test_consume_calls_only_activation_assessment_as_semantic_authority():
    source = textwrap.dedent(
        inspect.getsource(
            SystemdProductionActivationConsumptionStore
            .consume
        )
    )

    tree = ast.parse(
        source
    )

    calls = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if isinstance(
            node.func,
            ast.Name,
        ):
            calls.append(
                node.func.id
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            calls.append(
                node.func.attr
            )

    assert (
        calls.count(
            "assess"
        )
        == 1
    )

    for prohibited in (
        "evaluate",
        "evaluate_bound",
        "evaluate_systemd_production_bound",
        "production_runtime_guard",
        "invoke_explicit",
        "delegate_for_test",
        "execute",
        "execute_verified",
        "execute_argv",
        "acquire",
        "verify",
        "resolve",
    ):
        assert prohibited not in calls


def test_module_has_no_runtime_or_effect_authority():
    source = inspect.getsource(
        module
    )

    for token in (
        "SystemdCommanderIntegration",
        "SystemdProductionRuntimeDelegationBridge",
        "SystemdProductionExecutionDelegationBoundary",
        "ExecutionBoundary",
        "IncidentManager",
        "FinalOutcomeMapper",
        "subprocess",
        "systemctl",
        "sudo",
        "pkexec",
        "systemd-run",
    ):
        assert token not in source
