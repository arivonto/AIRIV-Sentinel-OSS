import ast
from concurrent.futures import ThreadPoolExecutor
import inspect
from threading import Barrier

import pytest

import sentinel.worker as public_api
from sentinel.worker import (
    DuplicateWorkerError,
    InvalidWorkerError,
    WorkerIdentityMismatchError,
    WorkerInfo,
    WorkerId,
    WorkerNotFoundError,
    WorkerProtocol,
    WorkerRegistry,
    WorkerRegistryError,
    WorkerState,
)
from sentinel.worker import registry as registry_module


class FakeWorker:
    def __init__(self, worker_id):
        self.identity = worker_id
        self.current_state = WorkerState.REGISTERED
        self.calls = []

    def worker_id(self):
        return self.identity

    def state(self):
        self.calls.append("state")
        return self.current_state

    def start(self):
        self.calls.append("start")
        self.current_state = WorkerState.RUNNING

    def stop(self):
        self.calls.append("stop")
        self.current_state = WorkerState.STOPPED

    def heartbeat(self):
        self.calls.append("heartbeat")
        raise AssertionError("Registry must not request a heartbeat")

    def health(self):
        self.calls.append("health")
        return True


def registration(value="worker-1"):
    worker_id = WorkerId(value)
    return FakeWorker(worker_id), WorkerInfo(worker_id, value, "1", "")


def test_empty_registry():
    registry = WorkerRegistry()
    assert len(registry) == 0
    assert not registry.contains(WorkerId("missing"))
    assert registry.worker_ids() == ()
    assert registry.workers() == ()
    assert registry.worker_infos() == ()


def test_register_and_lookup_have_no_worker_side_effects():
    registry = WorkerRegistry()
    worker, info = registration()
    assert isinstance(worker, WorkerProtocol)
    assert registry.register(worker, info) is None
    assert len(registry) == 1
    assert registry.contains(WorkerId("worker-1"))
    assert registry.get(WorkerId("worker-1")) is worker
    assert registry.get_info(WorkerId("worker-1")) is info
    assert worker.calls == []
    assert worker.current_state is WorkerState.REGISTERED


@pytest.mark.parametrize("operation,index", [
    ("worker_ids", None), ("workers", 0), ("worker_infos", 1),
])
def test_enumeration_is_ordered_immutable_snapshot(operation, index):
    registry = WorkerRegistry()
    entries = [registration(value) for value in ("z", "a", "m")]
    for worker, info in entries:
        registry.register(worker, info)
    snapshot = getattr(registry, operation)()
    expected = tuple(info.worker_id for _, info in entries) if index is None else tuple(
        entry[index] for entry in entries
    )
    assert isinstance(snapshot, tuple)
    assert snapshot == expected
    with pytest.raises(TypeError):
        snapshot[0] = None
    registry.unregister(entries[0][1].worker_id)
    registry.register(*entries[0])
    assert snapshot == expected
    assert getattr(registry, operation)() == expected[1:] + expected[:1]
    assert all(worker.calls == [] for worker, _ in entries)


@pytest.mark.parametrize("same_object", [True, False])
def test_duplicate_registration_preserves_original(same_object):
    registry = WorkerRegistry()
    worker, info = registration()
    registry.register(worker, info)
    replacement = worker if same_object else FakeWorker(WorkerId("worker-1"))
    replacement_info = WorkerInfo(info.worker_id, "Replacement", "2", "new")
    with pytest.raises(DuplicateWorkerError):
        registry.register(replacement, replacement_info)
    assert registry.workers() == (worker,)
    assert registry.worker_infos() == (info,)
    assert registry.get(info.worker_id) is worker
    assert registry.get_info(info.worker_id) is info
    assert worker.calls == replacement.calls == []


@pytest.mark.parametrize("invalid_kind", ["mismatch", "object", "incomplete", "info", "id"])
def test_failed_registration_leaves_registry_unchanged(invalid_kind):
    registry = WorkerRegistry()
    original, original_info = registration()
    registry.register(original, original_info)
    worker, info = registration("new")
    error = InvalidWorkerError
    if invalid_kind == "mismatch":
        worker = FakeWorker(WorkerId("different"))
        error = WorkerIdentityMismatchError
    elif invalid_kind == "object":
        worker = object()
    elif invalid_kind == "incomplete":
        class IncompleteWorker:
            def worker_id(self):
                return info.worker_id
        worker = IncompleteWorker()
    elif invalid_kind == "info":
        info = object()
    else:
        worker.identity = "new"
    with pytest.raises(error):
        registry.register(worker, info)
    assert len(registry) == 1
    assert registry.worker_ids() == (original_info.worker_id,)
    assert registry.workers() == (original,)
    assert registry.worker_infos() == (original_info,)


@pytest.mark.parametrize("operation", ["get", "get_info", "unregister"])
def test_unknown_identity_raises_not_found(operation):
    registry = WorkerRegistry()
    with pytest.raises(WorkerNotFoundError):
        getattr(registry, operation)(WorkerId("missing"))
    assert len(registry) == 0


def test_unregister_removes_worker_and_metadata_without_lifecycle_changes():
    registry = WorkerRegistry()
    worker, info = registration()
    registry.register(worker, info)
    assert registry.unregister(info.worker_id) is worker
    assert len(registry) == 0
    assert not registry.contains(info.worker_id)
    assert registry.worker_ids() == registry.workers() == registry.worker_infos() == ()
    for operation in (registry.get, registry.get_info, registry.unregister):
        with pytest.raises(WorkerNotFoundError):
            operation(info.worker_id)
    assert worker.calls == []
    assert worker.current_state is WorkerState.REGISTERED


@pytest.mark.parametrize("exception,category", [
    (DuplicateWorkerError, ValueError),
    (WorkerNotFoundError, LookupError),
    (WorkerIdentityMismatchError, ValueError),
    (InvalidWorkerError, ValueError),
])
def test_exception_hierarchy(exception, category):
    assert issubclass(exception, WorkerRegistryError)
    assert issubclass(exception, category)


def test_public_exports():
    expected = {
        "WorkerState", "WorkerTransitionError", "can_transition", "validate_transition",
        "WorkerId", "WorkerInfo", "WorkerHeartbeat", "WorkerProtocol",
        "WorkerRegistry", "WorkerRegistryError", "DuplicateWorkerError",
        "WorkerNotFoundError", "WorkerIdentityMismatchError", "InvalidWorkerError",
    }
    assert expected <= set(public_api.__all__)
    for name in expected:
        assert getattr(public_api, name) is not None


def test_concurrent_duplicate_registration_has_one_winner():
    registry = WorkerRegistry()
    barrier = Barrier(2)
    entries = [registration(), registration()]

    def attempt(entry):
        barrier.wait(timeout=5)
        try:
            registry.register(*entry)
        except DuplicateWorkerError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, entries))
    assert sorted(results) == [False, True]
    winner, info = entries[results.index(True)]
    assert len(registry) == 1
    assert registry.get(info.worker_id) is winner
    assert registry.get_info(info.worker_id) is info


def test_registry_architectural_boundary():
    source = inspect.getsource(registry_module)
    for forbidden in (
        "IncidentManager", "DiagnosisEvaluator", "Commander", "RemediationPolicy",
        "FinalOutcomeMapper", "RuntimeSupervisor", "HealthMonitor",
    ):
        assert forbidden not in source
    tree = ast.parse(source)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    for node in imports:
        assert isinstance(node, ast.ImportFrom)
        assert (node.level, node.module) in {
            (0, "dataclasses"), (0, "threading"), (1, "models"), (1, "protocol"),
        }
