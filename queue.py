from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from _queue import Empty, SimpleQueue


class Full(Exception):
    """Compatibility exception exposed by the standard queue module."""


@dataclass(frozen=True, slots=True)
class QueuedTask:
    id: str
    name: str
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "task_id": self.id,
            "task_type": self.name,
            "status": self.status,
        }
        data.update(self.metadata)
        return data


class ExecutionQueue:
    """Simple deterministic execution queue stored as YAML."""

    def __init__(
        self,
        tasks: list[QueuedTask] | None = None,
        path: str | Path | None = None,
        mission_id: str | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.mission_id = mission_id
        self._tasks: list[QueuedTask] = list(tasks or [])

    @classmethod
    def load(cls, path: str | Path) -> "ExecutionQueue":
        queue_path = Path(path)
        if not queue_path.exists():
            return cls(tasks=[], path=queue_path)
        raw = yaml.safe_load(queue_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("queue YAML must contain a mapping")

        mission_id = raw.get("mission_id")
        if not isinstance(mission_id, str) or not mission_id.strip():
            raise ValueError("queue YAML requires a non-empty mission_id")

        items = raw.get("tasks")
        if not isinstance(items, list):
            raise ValueError("queue YAML must contain a tasks list")

        tasks: list[QueuedTask] = []
        required = {
            "task_id",
            "task_type",
            "dependencies",
            "status",
            "success_condition",
            "allowed_files",
            "evidence",
        }
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"task at index {index} must be a mapping")
            missing = sorted(required - item.keys())
            if missing:
                raise ValueError(
                    f"task at index {index} is missing required fields: {', '.join(missing)}"
                )
            if "id" in item or "name" in item:
                raise ValueError(f"task at index {index} uses legacy fields")

            task_id = item["task_id"]
            task_type = item["task_type"]
            status = item["status"]
            if not all(
                isinstance(value, str) and value.strip()
                for value in (task_id, task_type, status, item["success_condition"])
            ):
                raise ValueError(f"task at index {index} has invalid scalar fields")
            if not isinstance(item["dependencies"], list):
                raise ValueError(f"task at index {index} dependencies must be a list")
            if not isinstance(item["allowed_files"], list):
                raise ValueError(f"task at index {index} allowed_files must be a list")
            if not isinstance(item["evidence"], dict):
                raise ValueError(f"task at index {index} evidence must be a mapping")
            metadata = {
                key: value
                for key, value in item.items()
                if key not in {"task_id", "task_type", "status"}
            }
            metadata.setdefault("depends_on", item["dependencies"])
            tasks.append(
                QueuedTask(
                    id=task_id,
                    name=task_type,
                    status=status,
                    metadata=metadata,
                )
            )

        return cls(tasks=tasks, path=queue_path, mission_id=mission_id)

    def save(self) -> None:
        if self.path is None:
            raise ValueError("queue path is not configured")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.mission_id:
            raise ValueError("mission_id is required")
        payload = {
            "mission_id": self.mission_id,
            "tasks": [task.to_dict() for task in self._tasks],
        }
        self.path.write_text(
            yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    def list_pending(self) -> list[QueuedTask]:
        return [task for task in self._tasks if task.status == "pending"]

    def next_task(self) -> QueuedTask | None:
        pending = self.list_pending()
        return pending[0] if pending else None

    def mark_complete(self, task_id: str, result: Any | None = None) -> QueuedTask:
        return self._update_status(task_id, "complete", result=result)

    def mark_failed(self, task_id: str, error: Any | None = None) -> QueuedTask:
        return self._update_status(task_id, "failed", error=error)

    def _update_status(
        self,
        task_id: str,
        new_status: str,
        **metadata: Any,
    ) -> QueuedTask:
        for index, task in enumerate(self._tasks):
            if task.id == task_id:
                updated = QueuedTask(
                    id=task.id,
                    name=task.name,
                    status=new_status,
                    metadata={**task.metadata, **metadata},
                )
                self._tasks[index] = updated
                return updated
        raise KeyError(f"task '{task_id}' not found")

    def __iter__(self):
        return iter(self._tasks)

    def __len__(self) -> int:
        return len(self._tasks)
