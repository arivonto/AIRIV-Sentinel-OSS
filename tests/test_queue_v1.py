from __future__ import annotations

import yaml

from queue import ExecutionQueue


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
    payload = {"mission_id": "TEST-MISSION", "tasks": canonical_tasks}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_load_queue_and_return_next_pending_task_in_order(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [
            {"id": "TASK-001", "name": "read", "status": "pending"},
            {"id": "TASK-002", "name": "write", "status": "pending"},
        ],
    )

    queue = ExecutionQueue.load(queue_file)

    assert [task.id for task in queue.list_pending()] == ["TASK-001", "TASK-002"]
    assert queue.next_task().id == "TASK-001"

    queue.mark_complete("TASK-001", {"result": "ok"})
    assert queue.next_task().id == "TASK-002"


def test_mark_failed_and_save_queue_state(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [
            {"id": "TASK-101", "name": "analyze", "status": "pending"},
            {"id": "TASK-102", "name": "repair", "status": "pending"},
        ],
    )

    queue = ExecutionQueue.load(queue_file)
    queue.mark_failed("TASK-101", "timed out")
    queue.save()

    persisted = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "failed"
    assert persisted["tasks"][0]["error"] == "timed out"
    assert persisted["tasks"][1]["status"] == "pending"
