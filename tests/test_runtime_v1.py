from __future__ import annotations

import yaml

from runtime import Runtime


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


def test_runtime_empty_queue_reports_empty(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [])

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.status == "empty"
    assert report.task_id is None
    assert report.updated_queue is False


def test_runtime_executes_one_pending_task(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [{"id": "TASK-1", "name": "first", "status": "pending"}])

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.status == "success"
    assert report.task_id == "TASK-1"
    assert report.verification == "PASS"
    assert report.updated_queue is True


def test_runtime_marks_failed_verification_and_saves_queue(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [{"id": "TASK-2", "name": "fail-me", "status": "pending"}])

    runtime = Runtime(queue_file)
    runtime.verifier = type("V", (), {"verify_success": lambda self, **kwargs: type("R", (), {"status": "FAIL", "details": {"reason": "missing success"}})()})()

    report = runtime.run_once()

    assert report.status == "failed"
    assert report.verification == "FAIL"
    persisted = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "failed"


def test_runtime_updates_queue_after_success(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [{"id": "TASK-3", "name": "complete", "status": "pending"}])

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.status == "success"
    persisted = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    assert persisted["tasks"][0]["status"] == "complete"


def test_runtime_report_contains_execution_details(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    _write_queue(queue_file, [{"id": "TASK-4", "name": "report", "status": "pending"}])

    runtime = Runtime(queue_file)
    report = runtime.run_once()

    assert report.details["execution"]["status"] == "success"
    assert report.details["worker"]["status"] == "completed"
    assert report.verification == "PASS"
