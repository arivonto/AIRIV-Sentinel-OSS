from __future__ import annotations

import yaml

from executor import ExecutionRequest, Executor
from queue import ExecutionQueue
from runtime import Runtime
from scheduler import Scheduler
from verifier import Verifier
from worker import Worker


def _write_queue(path, tasks):
    canonical_tasks = [
        {
            "task_id": task["id"],
            "task_type": task["name"],
            "dependencies": task.get("depends_on", []),
            "status": task.get("status", "pending"),
            "success_condition": "status",
            "allowed_files": [],
            "evidence": {},
        }
        for task in tasks
    ]
    path.write_text(
        yaml.safe_dump(
            {"mission_id": "TEST-MISSION", "tasks": canonical_tasks},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_runtime_kernel_single_cycle_success(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [{"id": "TASK-1", "name": "single-cycle", "status": "pending"}],
    )

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.status == "success"
    assert report.task_id == "TASK-1"
    assert report.verification == "PASS"
    assert report.updated_queue is True

    persisted = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "complete"


def test_runtime_kernel_rejects_empty_queue(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [])

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.status == "empty"
    assert report.task_id is None
    assert report.updated_queue is False


def test_runtime_kernel_failures_are_saved_to_queue(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [{"id": "TASK-2", "name": "failed-task", "status": "pending"}])

    runtime = Runtime(queue_file)
    runtime.verifier = type(
        "FailVerifier",
        (),
        {
            "verify_success": lambda self, **kwargs: type("Result", (), {"status": "FAIL", "details": {"reason": "missing success"}})()
        },
    )()

    report = runtime.run_once()

    assert report.status == "failed"
    assert report.verification == "FAIL"

    persisted = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "failed"


def test_kernel_components_are_wired_in_order():
    queue = ExecutionQueue(tasks=[ExecutionQueue.__dict__.get("_tasks", None) and []]) if False else ExecutionQueue(
        tasks=[]
    )
    queue._tasks = [
        type("Task", (), {"id": "TASK-3", "name": "ordered", "status": "pending", "metadata": {}})(),
    ]

    scheduler = Scheduler()
    scheduler._queue = queue
    worker = Worker()
    verifier = Verifier()
    executor = Executor()
    runtime = Runtime(queue_path="/tmp/kernel_runtime_test.yaml", scheduler=scheduler, worker=worker, verifier=verifier, executor=executor)

    queued = runtime.scheduler._queue
    assert queued is queue
    assert runtime.worker is worker
    assert runtime.verifier is verifier
    assert runtime.executor is executor


def test_runtime_kernel_compose_without_dangling_dependencies():
    runtime = Runtime(queue_path="/tmp/kernel_runtime_test_2.yaml")

    assert isinstance(runtime.scheduler, Scheduler)
    assert isinstance(runtime.worker, Worker)
    assert isinstance(runtime.verifier, Verifier)
    assert isinstance(runtime.executor, Executor)
    assert runtime.queue_path.name == "kernel_runtime_test_2.yaml"
