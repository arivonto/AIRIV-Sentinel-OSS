"""Repository-only canary tests: all effects and observations are fake."""
import dataclasses
import inspect
import json
import subprocess

import pytest

import sentinel.systemd_canary_live_execution as module
from sentinel.systemd_canary_live_execution import ARGV, COMPONENT, UNIT, CanaryLiveRequest, SystemdCanaryLiveExecution
from test_systemd_commander_integration_v1 import make_runtime, make_identity, make_snapshot


def payload():
    return dict(schema_version=1, request_id="request-1", approval_id="approval-1",
                created_at=1000, expires_at=1100, component_id=COMPONENT,
                unit=UNIT, action="RESTART", argv=list(ARGV),
                expected_pre_invocation_id="a" * 32)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Host execution forbidden")
    monkeypatch.setattr(subprocess, "run", forbidden)
    runtime, orchestrator, fake, integration = make_runtime(tmp_path, monkeypatch)
    target = dataclasses.replace(make_identity(), unit_name=UNIT,
                                 fragment_path="/etc/systemd/system/" + UNIT)
    before = make_snapshot(target=target)
    after = make_snapshot(target=target, invocation_id="b" * 32)
    snapshots = [before, after]
    calls = []
    def provider():
        calls.append(1)
        return snapshots[min(len(calls) - 1, len(snapshots) - 1)]
    surface = SystemdCanaryLiveExecution(runtime.commander, runtime.remediation_action_catalog,
                                        root=tmp_path / "inbox", snapshot_provider=provider,
                                        clock=lambda: 1050)
    plan = CanaryLiveRequest.parse(json.dumps(payload()), 1050).build_plan(before)
    fake.expected_command = orchestrator.identity_boundary._bound_command(plan.effect)
    return runtime, orchestrator, fake, surface, snapshots, calls, plan


def deliver(surface, data=None):
    surface.root.mkdir(exist_ok=True)
    surface.root.chmod(0o700)
    surface.request_path.write_text(json.dumps(payload() if data is None else data))
    surface.request_path.chmod(0o600)


def empty(runtime):
    assert runtime.policy.allowed_actions == set()
    assert runtime.policy.list_bound_runs() == ()
    assert runtime.remediation_action_catalog.list_actions() == ()
    assert runtime.remediation_action_catalog.list_triggers() == ()


def test_absence_is_inert(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    empty(runtime)
    assert surface.poll_once() is None
    assert not surface.root.exists()
    assert calls == fake.calls == []
    assert orch.identity_boundary.journal.get_live_run_permit(plan.effect.run_id) is None
    empty(runtime)


@pytest.mark.parametrize("field,value", [
    ("schema_version", True), ("schema_version", 2),
    ("component_id", "systemd:airiv-sentinel.service"),
    ("unit", "airiv-sentinel.service"), ("unit", "other.service"),
    ("action", "STOP"), ("argv", ["/usr/bin/systemctl", "restart", UNIT]),
    ("argv", list(ARGV) + ["other.service"]), ("expires_at", 1040),
    ("created_at", 1060), ("expires_at", 2000), ("expires_at", float("nan")),
    ("request_id", "../escape"), ("request_id", "x" * 65),
    ("approval_id", ""), ("approval_id", "x" * 65),
    ("expected_pre_invocation_id", "0" * 32),
])
def test_invalid_request_fails_closed(setup, field, value):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    data = payload()
    data[field] = value
    deliver(surface, data)
    assert surface.poll_once() is None
    assert fake.calls == calls == []
    empty(runtime)


@pytest.mark.parametrize("raw", ["{", "[]", "{}", "x" * 4097,
    json.dumps(payload())[:-1] + ', "action": "RESTART"}'])
def test_malformed(setup, raw):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    deliver(surface)
    surface.request_path.write_text(raw)
    assert surface.poll_once() is None
    assert fake.calls == calls == []
    empty(runtime)


@pytest.mark.parametrize("change", ["invocation", "inactive", "unloaded", "weak", "foreign"])
def test_bad_pre_snapshot(setup, change):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    before = snaps[0]
    if change == "invocation":
        before = dataclasses.replace(before, invocation_id="c" * 32)
    elif change == "inactive":
        before = dataclasses.replace(before, active_state="inactive")
    elif change == "unloaded":
        before = dataclasses.replace(before, load_state="not-found")
    elif change == "weak":
        weak = dataclasses.replace(before.identity)
        object.__setattr__(weak, "fragment_inode", 0)
        before = dataclasses.replace(before, identity=weak)
    else:
        before = dataclasses.replace(before, identity=make_identity())
    snaps[0] = before
    deliver(surface)
    assert surface.poll_once() is None
    assert fake.calls == []
    assert orch.identity_boundary.journal.get_live_run_permit(plan.effect.run_id) is None
    empty(runtime)


def test_exact_success_single_authorities(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    empty(runtime)
    assert plan.effect.argv == ARGV
    assert plan.effect.component_id == COMPONENT
    assert plan.permit_binding.matches(plan.effect)
    counts = dict(policy=0, adapter=0, permit=0)
    for obj, method, key in [(runtime.policy, "evaluate_bound", "policy"),
                             (surface.integration.execution_adapter, "execute", "adapter"),
                             (orch.identity_boundary.journal, "claim_live_run_permit", "permit")]:
        original = getattr(obj, method)
        def counted(*args, _original=original, _key=key, **kwargs):
            counts[_key] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(obj, method, counted)
    deliver(surface)
    result = surface.poll_once()
    assert result.recovered
    assert counts == dict(policy=1, adapter=1, permit=1)
    assert len(fake.calls) == 1 and fake.calls[0][0] == ARGV
    assert len(calls) == 2
    assert not surface.request_path.exists()
    assert surface.poll_once() is None
    empty(runtime)


@pytest.mark.parametrize("post", ["unchanged", "foreign", "inactive", "unloaded", "invalid", "exception"])
def test_independent_verification_and_cleanup(setup, post):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    if post == "unchanged":
        snaps[1] = snaps[0]
    elif post == "foreign":
        snaps[1] = dataclasses.replace(snaps[1], identity=make_identity())
    elif post == "inactive":
        snaps[1] = dataclasses.replace(snaps[1], active_state="inactive")
    elif post == "unloaded":
        snaps[1] = dataclasses.replace(snaps[1], load_state="not-found")
    elif post == "invalid":
        snaps[1] = None
    else:
        def provider():
            calls.append(1)
            if len(calls) > 1:
                raise RuntimeError("observation failed")
            return snaps[0]
        surface.snapshot_provider = provider
    deliver(surface)
    result = surface.poll_once()
    assert result is None or not result.recovered
    assert len(fake.calls) == 1
    assert len(calls) == 2
    empty(runtime)


def test_execution_failure_cleanup(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    fake.success = False
    deliver(surface)
    assert not surface.poll_once().recovered
    assert len(calls) == len(fake.calls) == 1
    empty(runtime)


@pytest.mark.parametrize("crash", [False, True])
def test_durable_replay_after_reconstruction(setup, crash, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    if crash:
        original = orch.identity_boundary.journal.claim
        def interrupted(**kwargs):
            raise RuntimeError("crash after durable permit, before execution identity")
        monkeypatch.setattr(orch.identity_boundary.journal, "claim", interrupted)
    deliver(surface)
    surface.poll_once()
    if crash:
        monkeypatch.setattr(orch.identity_boundary.journal, "claim", original)
    assert orch.identity_boundary.journal.get_live_run_permit(plan.effect.run_id) is not None
    from sentinel.remediation_execution_identity import RemediationExecutionIdentityJournal
    orch.identity_boundary.journal = RemediationExecutionIdentityJournal(orch.identity_boundary.journal.root)
    retry = SystemdCanaryLiveExecution(runtime.commander, runtime.remediation_action_catalog,
                                      root=surface.root, snapshot_provider=lambda: snaps[0], clock=lambda: 1050)
    deliver(retry)
    retry.poll_once()
    assert len(fake.calls) == (0 if crash else 1)
    empty(runtime)


def test_request_immutable(setup):
    request = CanaryLiveRequest.parse(json.dumps(payload()), 1050)
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.unit = "other.service"
    assert isinstance(request.argv, tuple)


def test_runtime_wiring_absent(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    runtime.canary_live_execution = surface
    runtime.running = True
    monkeypatch.setattr(runtime.sensor_adapter, "process_tick", lambda: [])
    monkeypatch.setattr(runtime.diagnostic, "submit", lambda incidents: None)
    assert runtime.run_once() == []
    assert fake.calls == calls == []
    empty(runtime)


def test_source_uses_only_integration():
    source = inspect.getsource(module)
    for forbidden in ("shell=True", "sudo", "pkexec", "systemd-run", "os.system", ".execute(", "evaluate_bound("):
        assert forbidden not in source
    assert source.count(".execute_verified(") == 1


@pytest.mark.parametrize("changed", ["request_id", "approval_id"])
def test_reuse_of_either_consumed_identity_cannot_repeat_effect(setup, changed):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    deliver(surface)
    assert surface.poll_once().recovered
    surface.snapshot_provider = lambda: snaps[0]
    data = payload()
    data[changed] = "different-id"
    deliver(surface, data)
    surface.poll_once()
    assert len(fake.calls) == 1
    empty(runtime)


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "writable", "directory", "root_symlink"])
def test_unsafe_inbox_objects(setup, unsafe, tmp_path):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    deliver(surface)
    if unsafe in ("symlink", "hardlink"):
        other = tmp_path / "other.json"
        surface.request_path.rename(other)
        if unsafe == "symlink":
            surface.request_path.symlink_to(other)
        else:
            surface.request_path.hardlink_to(other)
    elif unsafe == "writable":
        surface.request_path.chmod(0o666)
    elif unsafe == "directory":
        surface.request_path.unlink()
        surface.request_path.mkdir()
    else:
        moved = tmp_path / "moved"
        surface.root.rename(moved)
        surface.root.symlink_to(moved, target_is_directory=True)
    assert surface.poll_once() is None
    assert calls == fake.calls == []
    empty(runtime)


def test_expiration_during_pre_observation(setup):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    times = iter([1050, 1100])
    surface.clock = lambda: next(times)
    deliver(surface)
    assert surface.poll_once() is None
    assert fake.calls == []
    empty(runtime)


def test_policy_denial_cleanup(setup, monkeypatch):
    runtime, orch, fake, surface, snaps, calls, plan = setup
    original = runtime.policy.evaluate_bound
    def deny(**kwargs):
        runtime.policy.allowed_actions.clear()
        return original(**kwargs)
    monkeypatch.setattr(runtime.policy, "evaluate_bound", deny)
    deliver(surface)
    result = surface.poll_once()
    assert not result.authorization.authorized
    assert fake.calls == []
    empty(runtime)


def test_concurrent_delivery_delegates_once(setup):
    from concurrent.futures import ThreadPoolExecutor
    runtime, orch, fake, surface, snaps, calls, plan = setup
    other = SystemdCanaryLiveExecution(runtime.commander, runtime.remediation_action_catalog,
                                      root=surface.root, snapshot_provider=surface.snapshot_provider,
                                      clock=lambda: 1050)
    deliver(surface)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda obj: obj.poll_once(), [surface, other]))
    assert sum(result is not None and result.recovered for result in results) == 1
    assert len(fake.calls) == 1
    empty(runtime)
