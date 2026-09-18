from __future__ import annotations

import yaml

from scheduler import Scheduler


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


def test_scheduler_next_pending_task_preserves_order(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [
            {"id": "TASK-1", "name": "first", "status": "pending"},
            {"id": "TASK-2", "name": "second", "status": "pending"},
        ],
    )

    scheduler = Scheduler(queue_file)

    assert scheduler.next_task().id == "TASK-1"
    assert scheduler.can_execute("TASK-1") is True
    scheduler.mark_completed("TASK-1", {"result": "ok"})
    assert scheduler.next_task().id == "TASK-2"


def test_scheduler_validates_dependencies_before_execution(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [
            {"id": "TASK-A", "name": "setup", "status": "pending"},
            {"id": "TASK-B", "name": "run", "status": "pending", "depends_on": ["TASK-A"]},
        ],
    )

    scheduler = Scheduler(queue_file)

    assert scheduler.can_execute("TASK-A") is True
    assert scheduler.can_execute("TASK-B") is False
    scheduler.mark_completed("TASK-A")
    assert scheduler.can_execute("TASK-B") is True
    assert scheduler.next_task().id == "TASK-B"


def test_scheduler_detects_mission_complete_and_failed_tasks(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(
        queue_file,
        [
            {"id": "TASK-1", "name": "one", "status": "pending"},
            {"id": "TASK-2", "name": "two", "status": "pending"},
        ],
    )

    scheduler = Scheduler(queue_file)
    scheduler.mark_completed("TASK-1")
    scheduler.mark_completed("TASK-2")
    assert scheduler.mission_complete() is True

    queue_file2 = tmp_path / "queue-fail.yaml"
    _write_queue(
        queue_file2,
        [{"id": "TASK-X", "name": "bad", "status": "pending"}],
    )
    scheduler2 = Scheduler(queue_file2)
    scheduler2.mark_failed("TASK-X", "boom")
    assert scheduler2.mission_complete() is False
    assert scheduler2.next_task() is None
