from __future__ import annotations

import yaml
import pytest

from queue import ExecutionQueue


REQUIRED_TASK = {
    "task_id": "TASK-001",
    "task_type": "echo",
    "dependencies": [],
    "status": "pending",
    "success_condition": "execution.status == success",
    "allowed_files": [],
    "evidence": {},
}


def write_queue(path, task):
    path.write_text(
        yaml.safe_dump(
            {"mission_id": "MISSION-001", "tasks": [task]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_canonical_queue_loads_successfully(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    write_queue(queue_file, REQUIRED_TASK)

    queue = ExecutionQueue.load(queue_file)

    assert queue.mission_id == "MISSION-001"
    assert queue.next_task().id == "TASK-001"
    assert queue.next_task().name == "echo"


@pytest.mark.parametrize("missing_field", ["task_id", "task_type"])
def test_missing_required_task_fields_fail(tmp_path, missing_field):
    queue_file = tmp_path / "queue.yaml"
    task = dict(REQUIRED_TASK)
    task.pop(missing_field)
    write_queue(queue_file, task)

    with pytest.raises(ValueError, match="missing required fields"):
        ExecutionQueue.load(queue_file)


def test_legacy_id_name_format_fails(tmp_path):
    queue_file = tmp_path / "queue.yaml"
    write_queue(
        queue_file,
        {
            "id": "TASK-001",
            "name": "echo",
            "status": "pending",
        },
    )

    with pytest.raises(ValueError, match="missing required fields"):
        ExecutionQueue.load(queue_file)
