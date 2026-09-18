from __future__ import annotations

from pathlib import Path
from typing import Any

from queue import ExecutionQueue, QueuedTask


class Scheduler:
    """Deterministic orchestration layer over the YAML-backed execution queue."""

    def __init__(self, queue_path: str | Path | None = None) -> None:
        self.queue_path = Path(queue_path) if queue_path is not None else None
        self._queue: ExecutionQueue | None = None
        if self.queue_path is not None:
            self.load_queue(self.queue_path)

    def load_queue(self, queue_path: str | Path | None = None) -> ExecutionQueue:
        path = Path(queue_path) if queue_path is not None else self.queue_path
        if path is None:
            raise ValueError("queue path is required")
        self._queue = ExecutionQueue.load(path)
        self.queue_path = path
        return self._queue

    def next_task(self) -> QueuedTask | None:
        if self._queue is None:
            raise ValueError("queue is not loaded")
        for task in self._queue:
            if task.status == "pending" and self.can_execute(task):
                return task
        return None

    def can_execute(self, task: QueuedTask | str) -> bool:
        if self._queue is None:
            raise ValueError("queue is not loaded")
        resolved = self._resolve_task(task)
        if resolved.status != "pending":
            return False

        deps = self._dependency_ids(resolved)
        for dep_id in deps:
            dependency = self._find_task(dep_id)
            if dependency is None or dependency.status != "complete":
                return False
        return True

    def mark_completed(self, task: QueuedTask | str, result: Any | None = None) -> QueuedTask:
        if self._queue is None:
            raise ValueError("queue is not loaded")
        resolved = self._resolve_task(task)
        updated = self._queue.mark_complete(resolved.id, result=result)
        self._queue.save()
        return updated

    def mark_failed(self, task: QueuedTask | str, error: Any | None = None) -> QueuedTask:
        if self._queue is None:
            raise ValueError("queue is not loaded")
        resolved = self._resolve_task(task)
        updated = self._queue.mark_failed(resolved.id, error=error)
        self._queue.save()
        return updated

    def mission_complete(self) -> bool:
        if self._queue is None:
            return False
        return all(task.status == "complete" for task in self._queue)

    def _resolve_task(self, task: QueuedTask | str) -> QueuedTask:
        if isinstance(task, QueuedTask):
            return self._find_task(task.id) or task
        found = self._find_task(task)
        if found is None:
            raise KeyError(f"task '{task}' not found")
        return found

    def _find_task(self, task_id: str) -> QueuedTask | None:
        for task in self._queue or ():
            if task.id == task_id:
                return task
        return None

    @staticmethod
    def _dependency_ids(task: QueuedTask) -> list[str]:
        raw = task.metadata.get("depends_on", [])
        if raw is None:
            return []
        if isinstance(raw, str):
            return [raw]
        if isinstance(raw, (list, tuple, set)):
            return [str(item) for item in raw]
        return [str(raw)]
