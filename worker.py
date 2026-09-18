from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class WorkerResult:
    task_id: str
    task_name: str
    status: str
    result: Any = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "status": self.status,
            "result": self.result,
            "evidence": self.evidence,
        }


class Worker:
    """Deterministic single-task executor that does not decide policy or verify outcomes."""

    def execute(self, task: dict[str, Any] | None) -> WorkerResult:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")

        task_id = str(task.get("id", "")).strip()
        task_name = str(task.get("name", "")).strip()
        if not task_id or not task_name:
            raise ValueError("task must include non-empty id and name")

        dispatch_result = self.dispatch(task)
        collected = self.collect_result(task, dispatch_result)
        return WorkerResult(
            task_id=task_id,
            task_name=task_name,
            status="completed",
            result=collected.get("result"),
            evidence=collected.get("evidence", {}),
        )

    def dispatch(self, task: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")

        task_id = str(task.get("id", "")).strip()
        task_name = str(task.get("name", "")).strip()
        if not task_id or not task_name:
            raise ValueError("task must include non-empty id and name")

        return {
            "task_id": task_id,
            "task_name": task_name,
            "dispatched": True,
            "kind": "deterministic",
        }

    def collect_result(
        self,
        task: dict[str, Any],
        dispatch_result: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(task, dict):
            raise TypeError("task must be a dict")
        if not isinstance(dispatch_result, dict):
            raise TypeError("dispatch_result must be a dict")

        result = {
            "task_id": str(task.get("id", "")).strip(),
            "task_name": str(task.get("name", "")).strip(),
            "dispatch": dispatch_result,
            "result": {"status": "ok"},
        }
        return {
            "result": result["result"],
            "evidence": {
                "task_id": result["task_id"],
                "task_name": result["task_name"],
                "dispatch": dispatch_result,
            },
        }
