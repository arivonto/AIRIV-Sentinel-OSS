from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any

from executor import ExecutionRequest
from executor_factory import ExecutorFactory
from queue import ExecutionQueue
from scheduler import Scheduler
from verifier import Verifier
from worker import Worker


@dataclass(frozen=True, slots=True)
class RuntimeReport:
    queue_path: str | None
    status: str
    task_id: str | None
    task_name: str | None
    verification: str | None
    updated_queue: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_path": self.queue_path,
            "status": self.status,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "verification": self.verification,
            "updated_queue": self.updated_queue,
            "details": self.details,
        }


class Runtime:
    """Single-cycle deterministic runtime that orchestrates queue, scheduler, worker, executor, and verifier."""

    def __init__(
        self,
        queue_path: str | Path,
        *,
        scheduler: Scheduler | None = None,
        worker: Worker | None = None,
        verifier: Verifier | None = None,
        executor: Any | None = None,
        executor_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.queue_path = Path(queue_path)
        self.scheduler = scheduler or Scheduler(self.queue_path)
        self.worker = worker or Worker()
        self.verifier = verifier or Verifier()
        self.executor = executor or ExecutorFactory.create(
            executor_config or {"provider": "local"}
        )

    def run_once(self) -> RuntimeReport:
        queue = self.scheduler.load_queue(self.queue_path)
        task = self.scheduler.next_task()
        if task is None:
            return RuntimeReport(
                queue_path=str(self.queue_path),
                status="empty",
                task_id=None,
                task_name=None,
                verification=None,
                updated_queue=False,
                details={"reason": "no pending task"},
            )

        execution_request = ExecutionRequest(
            task_id=task.id,
            task_name=task.name,
            payload={"metadata": task.metadata},
        )
        execution_result = self.executor.execute(execution_request)
        worker_result = self.worker.execute({
            "id": task.id,
            "name": task.name,
            "payload": {"execution": execution_result.to_dict()},
        })

        verification = self.verifier.verify_success(
            task={"id": task.id, "name": task.name},
            success_condition="status",
            evidence={
                "task_id": task.id,
                "task_name": task.name,
                "worker_result": worker_result.to_dict(),
                "execution_result": execution_result.to_dict(),
            },
        )

        if verification.status == "FAIL":
            self.scheduler.mark_failed(task.id, verification.details)
            queue.save()
            return RuntimeReport(
                queue_path=str(self.queue_path),
                status="failed",
                task_id=task.id,
                task_name=task.name,
                verification="FAIL",
                updated_queue=True,
                details={"verification": verification.details},
            )

        self.scheduler.mark_completed(task.id, execution_result.to_dict())
        queue.save()
        return RuntimeReport(
            queue_path=str(self.queue_path),
            status="success",
            task_id=task.id,
            task_name=task.name,
            verification="PASS",
            updated_queue=True,
            details={
                "execution": execution_result.to_dict(),
                "worker": worker_result.to_dict(),
                "verification": verification.details,
            },
        )
