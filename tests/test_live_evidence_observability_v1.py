"""Live evidence identity and read-only production integration contract."""

import ast
import inspect
import json
import os
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sentinel.runtime import SentinelRuntime
from sentinel.worker import capability_worker, composition, entrypoint, observability
from sentinel.worker.capability_worker import SentinelCapabilityWorker
from sentinel.worker.observability import LiveEvidenceObservability


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, "REPOSITORY_ROOT", tmp_path)
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("AIRIV_SENTINEL_DIAGNOSTIC_DIR", str(tmp_path / "diagnostic"))
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "GNOME_DESKTOP_SESSION_ID",
                 "DBUS_SESSION_BUS_ADDRESS", "XDG_CURRENT_DESKTOP", "DESKTOP_SESSION"):
        monkeypatch.delenv(name, raising=False)


def status(writer, iteration=1):
    writer.status(worker_id="sentinel.capability", state="RUNNING", iteration=iteration,
                  last_cycle_at=None, last_cycle_status="OK", last_error_type=None)
    return json.loads((writer.root / "capability_status.json").read_text())


def records(writer):
    return [json.loads(line) for line in
            (writer.root / "live_observations.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("invocation", [None, "", "exact-systemd-ID-01234"])
def test_identity_is_never_invented(invocation, monkeypatch):
    if invocation is None:
        monkeypatch.delenv("INVOCATION_ID", raising=False)
    else:
        monkeypatch.setenv("INVOCATION_ID", invocation)
    writer = LiveEvidenceObservability()
    record = status(writer)
    assert record["pid"] == os.getpid()
    assert record["invocation_id"] == invocation
    assert record["schema_version"] == 1
    assert record["iteration"] == 1 and record["last_cycle_status"] == "OK"


def test_default_path_is_repo_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(observability, "REPOSITORY_ROOT", Path(observability.__file__).resolve().parents[2])
    monkeypatch.delenv("AIRIV_SENTINEL_RUNTIME_DIR")
    monkeypatch.chdir(tmp_path)
    assert LiveEvidenceObservability().root == Path(observability.__file__).resolve().parents[2] / "var/runtime"


def test_storage_rejects_external_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", str(tmp_path.parent / "outside"))
    with pytest.raises(ValueError, match="repository-local"):
        LiveEvidenceObservability()


def test_relative_override_is_repository_local(monkeypatch):
    monkeypatch.setenv("AIRIV_SENTINEL_RUNTIME_DIR", "var/custom-runtime")
    assert LiveEvidenceObservability().root == observability.REPOSITORY_ROOT / "var/custom-runtime"


def test_journal_symlink_is_not_followed(tmp_path):
    writer = LiveEvidenceObservability()
    writer.root.mkdir()
    target = tmp_path / "untouched"
    target.write_text("original")
    (writer.root / "live_observations.jsonl").symlink_to(target)
    runtime = SimpleNamespace(diagnostic=SimpleNamespace(store=SimpleNamespace(recover=lambda: [])))
    writer.observations(runtime, [SimpleNamespace(component_id="%1", incident_id="id")],
                        worker_id="w", iteration=1)
    assert target.read_text() == "original"


def test_exact_status_schema_and_new_component_retention():
    writer = LiveEvidenceObservability()
    assert set(status(writer)) == {
        "schema_version", "worker_id", "pid", "invocation_id", "state", "iteration",
        "last_cycle_at", "last_cycle_status", "last_error_type",
    }
    runtime = SimpleNamespace(diagnostic=SimpleNamespace(store=SimpleNamespace(recover=lambda: [])))
    items = [SimpleNamespace(component_id=pane, incident_id=None) for pane in ("%1", "%2")]
    for iteration in (1, 2):
        writer.observations(runtime, items, worker_id="w", iteration=iteration)
    assert [record["component_id"] for record in records(writer)] == ["%1", "%2"]


def drive(runtime, monkeypatch, writer, cycles=1):
    worker = SentinelCapabilityWorker(runtime, observability=writer)
    waits = iter([False] * cycles + [True])
    monkeypatch.setattr(worker._stop_event, "wait", lambda interval: next(waits))
    worker.start()
    worker._thread.join(3)
    assert not worker._thread.is_alive()
    return worker


def test_real_canonical_correlation_and_single_cycle(monkeypatch):
    runtime = SentinelRuntime()
    runtime.running = True  # No diagnostic thread or external execution.
    monkeypatch.setattr(runtime.sensor_adapter.parser, "inspect_panes", lambda: [{
        "source": "TMUX", "pane_id": "%exact-pane", "pane_dead": True,
        "capture_ok": False, "current_command": "bash", "window_name": "test",
        "first_observation": True,
    }])
    for owner, name in ((runtime.incident_manager, "evaluate_anomaly"),
                        (runtime.incident_manager, "resolve"), (runtime, "remediate"),
                        (runtime.policy, "evaluate"), (runtime.execution, "execute")):
        monkeypatch.setattr(owner, name, Mock(side_effect=AssertionError("forbidden")))
    for owner in (type(runtime), type(runtime.incident_manager),
                  type(runtime.commander), type(runtime.diagnostic)):
        monkeypatch.setattr(owner, "__init__", Mock(side_effect=AssertionError("duplicate")))
    original = runtime.run_once
    cycle = Mock(wraps=original)
    monkeypatch.setattr(runtime, "run_once", cycle)
    writer = LiveEvidenceObservability()
    worker = drive(runtime, monkeypatch, writer)
    try:
        cycle.assert_called_once_with()
        record, = records(writer)
        incident = runtime.incident_manager.get_active_incident("%exact-pane")
        investigation, = runtime.diagnostic.store.recover()
        assert record["component_id"] == "%exact-pane"
        assert record["incident_id"] == incident.incident_id == investigation.incident_id
        assert record["investigation_id"] == investigation.investigation_id
        assert record["correlation_status"] == "CORRELATED"
        assert record["pid"] == os.getpid()
        assert record["invocation_id"] == os.environ.get("INVOCATION_ID")
        assert record["iteration"] == 1
        persisted = json.loads((writer.root / "capability_status.json").read_text())
        assert persisted["last_cycle_status"] == "OK"
        assert persisted["last_cycle_at"] is not None
    finally:
        worker.stop()
    assert json.loads((writer.root / "capability_status.json").read_text())["state"] == "STOPPED"


def test_failure_externalizes_type_only(monkeypatch):
    runtime = SimpleNamespace(running=True, run_once=Mock(side_effect=RuntimeError("SECRET raw payload")))
    writer = LiveEvidenceObservability()
    worker = drive(runtime, monkeypatch, writer)
    record = json.loads((writer.root / "capability_status.json").read_text())
    assert record["state"] == record["last_cycle_status"] == "FAILED"
    assert record["last_error_type"] == "RuntimeError"
    assert record["iteration"] == 1
    assert "SECRET" not in (writer.root / "capability_status.json").read_text()
    assert not (writer.root / "live_observations.jsonl").exists()
    runtime.run_once.assert_called_once_with()


def test_first_observation_dedup_and_later_correlation():
    writer = LiveEvidenceObservability()
    recover = Mock(return_value=[])
    runtime = SimpleNamespace(diagnostic=SimpleNamespace(store=SimpleNamespace(recover=recover)))
    item = SimpleNamespace(component_id="%7", incident_id="canonical")
    def emit(iteration, items):
        writer.observations(runtime, items, worker_id="sentinel.capability", iteration=iteration)
    emit(1, [])
    emit(2, [item])
    emit(3, [item])
    first, = records(writer)
    assert first["iteration"] == 2
    assert first["investigation_id"] is None
    assert first["correlation_status"] == "INVESTIGATION_UNAVAILABLE"
    recover.return_value = [SimpleNamespace(component_id="%7", incident_id="canonical", investigation_id="real")]
    emit(4, [item])
    emit(5, [item])
    assert len(records(writer)) == 2
    assert records(writer)[1]["investigation_id"] == "real"
    item.anomaly_type = "changed"
    emit(6, [item])
    assert len(records(writer)) == 3


@pytest.mark.parametrize("kind", ["missing", "ambiguous", "failed", "mismatch"])
def test_unavailable_correlation_is_explicit(kind):
    writer = LiveEvidenceObservability()
    item = SimpleNamespace(component_id="%7", incident_id=None if kind == "missing" else "id")
    match = SimpleNamespace(component_id="%7", incident_id="id", investigation_id="real")
    recover = Mock(return_value=[match, match] if kind == "ambiguous" else [])
    if kind == "failed":
        recover.side_effect = RuntimeError("SECRET")
    if kind == "mismatch":
        recover.return_value = [SimpleNamespace(component_id="%other", incident_id="id", investigation_id="wrong")]
    runtime = SimpleNamespace(diagnostic=SimpleNamespace(store=SimpleNamespace(recover=recover)))
    writer.observations(runtime, [item], worker_id="w", iteration=1)
    record, = records(writer)
    assert record["investigation_id"] is None
    assert record["correlation_status"] == {
        "missing": "INCIDENT_UNAVAILABLE", "ambiguous": "INVESTIGATION_AMBIGUOUS",
        "failed": "INVESTIGATION_LOOKUP_FAILED", "mismatch": "INVESTIGATION_UNAVAILABLE",
    }[kind]
    assert "SECRET" not in (writer.root / "live_observations.jsonl").read_text()


def test_status_atomic_for_concurrent_reader():
    writer = LiveEvidenceObservability()
    status(writer, 0)
    failures = []
    def publish():
        for iteration in range(1, 51):
            status(writer, iteration)
    thread = Thread(target=publish)
    thread.start()
    while thread.is_alive():
        try:
            json.loads((writer.root / "capability_status.json").read_text())
        except Exception as error:
            failures.append(error)
    thread.join()
    assert not failures
    assert json.loads((writer.root / "capability_status.json").read_text())["iteration"] == 50


def test_write_failure_does_not_poison_dedup(tmp_path, monkeypatch):
    writer = LiveEvidenceObservability()
    item = SimpleNamespace(component_id="%1", incident_id="id")
    runtime = SimpleNamespace(diagnostic=SimpleNamespace(store=SimpleNamespace(recover=lambda: [])))
    with monkeypatch.context() as patch:
        patch.setattr(Path, "mkdir", Mock(side_effect=OSError("SECRET")))
        writer.observations(runtime, [item], worker_id="w", iteration=1)
        status_args = dict(worker_id="w", state="RUNNING", iteration=1,
                           last_cycle_at=None, last_cycle_status="OK", last_error_type=None)
        writer.status(**status_args)
    writer.observations(runtime, [item], worker_id="w", iteration=2)
    assert len(records(writer)) == 1


def test_production_composition_has_one_runtime():
    runtime = SentinelRuntime()
    bundle = composition.build_production_supervision(runtime, entrypoint.build_production_config())
    assert bundle.runtime is bundle.runtime_worker.runtime is bundle.capability_worker.runtime
    assert isinstance(bundle.capability_worker._observability, LiveEvidenceObservability)


def test_pane_observation_survives_later_lifecycle_evidence(monkeypatch):
    from sentinel.incidents.manager import Incident

    incident = Incident("canonical", "%7", "UNKNOWN", "FAILED")
    incident.add_evidence({"pane_id": "%7", "source": "TMUX",
                           "output_sha256": "first"}, "sensor")
    incident.add_evidence({}, "operator note", "OPERATOR_NOTE")
    runtime = SimpleNamespace(
        running=True, run_once=Mock(return_value=[incident]),
        diagnostic=SimpleNamespace(store=SimpleNamespace(recover=lambda: [])),
    )
    writer = LiveEvidenceObservability()
    worker = drive(runtime, monkeypatch, writer, cycles=3)
    try:
        assert runtime.run_once.call_count == 3
        first, = records(writer)
        assert first["iteration"] == 1
        assert first["source"] == "TMUX"
        assert first["component_id"] == "%7"
        incident.add_evidence({"pane_id": "%7", "source": "TMUX",
                               "output_sha256": "changed"}, "sensor")
        incident.add_evidence({}, "terminal note", "OPERATOR_NOTE")
        writer.observations(runtime, [incident], worker_id=worker.ID.value, iteration=4)
        first, changed = records(writer)
        assert first["observation_fingerprint"] != changed["observation_fingerprint"]
    finally:
        worker.stop()


def test_structural_audit():
    sources = [inspect.getsource(module) for module in
               (observability, capability_worker, composition, entrypoint)]
    for source in sources:
        for forbidden in ("IncidentManager(", "CommanderOrchestrator(",
                          "RuntimeDiagnosticCoordinator(", "evaluate_anomaly(",
                          ".resolve(", ".remediate(", "systemctl", "subprocess"):
            assert forbidden not in source
    calls = [node for source in sources for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Call)]
    assert sum(isinstance(node.func, ast.Name) and node.func.id == "SentinelRuntime" for node in calls) == 1
    assert sum(isinstance(node.func, ast.Attribute) and node.func.attr == "run_once" for node in calls) == 1
    observer_calls = [node.func.attr for node in ast.walk(ast.parse(sources[0]))
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not set(observer_calls) & {"submit", "register_incident", "start", "evaluate", "execute", "verify", "assess"}
