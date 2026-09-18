from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SafetyGateResult:
    allowed: bool
    reason: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "details": self.details,
        }


class SafetyGate:
    """Deterministic guard for allowed file scope, approved task scope, evidence, and task status."""

    def __init__(
        self,
        *,
        allowed_files: tuple[str, ...] = (),
        approved_tasks: tuple[str, ...] = (),
        valid_statuses: tuple[str, ...] = ("pending", "complete", "failed"),
    ) -> None:
        self.allowed_files = tuple(allowed_files)
        self.approved_tasks = tuple(approved_tasks)
        self.valid_statuses = tuple(valid_statuses)

    def check_task_scope(self, task_id: str | None, *, approved_tasks: tuple[str, ...] | None = None) -> SafetyGateResult:
        if not task_id:
            return SafetyGateResult(False, "missing task id", {"task_id": task_id})
        allowed = tuple(approved_tasks if approved_tasks is not None else self.approved_tasks)
        if not allowed:
            return SafetyGateResult(True, None, {"task_id": task_id})
        if task_id not in allowed:
            return SafetyGateResult(False, "task outside approved scope", {"task_id": task_id, "approved_tasks": list(allowed)})
        return SafetyGateResult(True, None, {"task_id": task_id})

    def check_modified_files(self, changed_files: list[str] | tuple[str, ...] | None, *, allowed_files: tuple[str, ...] | None = None) -> SafetyGateResult:
        files = list(changed_files or [])
        allowed = tuple(allowed_files if allowed_files is not None else self.allowed_files)
        if not files:
            return SafetyGateResult(False, "no modified files supplied", {"changed_files": files})
        if not allowed:
            return SafetyGateResult(True, None, {"changed_files": files})
        unexpected = [path for path in files if path not in allowed]
        if unexpected:
            return SafetyGateResult(False, "unexpected modified files", {"unexpected": unexpected, "allowed": list(allowed)})
        return SafetyGateResult(True, None, {"changed_files": files})

    def check_verification_evidence(self, evidence: dict[str, Any] | None) -> SafetyGateResult:
        if not isinstance(evidence, dict):
            return SafetyGateResult(False, "missing verification evidence", {"evidence": evidence})
        if not evidence:
            return SafetyGateResult(False, "missing verification evidence", {"evidence": evidence})
        return SafetyGateResult(True, None, {"evidence": evidence})

    def check_task_status(self, status: str | None, *, valid_statuses: tuple[str, ...] | None = None) -> SafetyGateResult:
        if status is None:
            return SafetyGateResult(False, "missing task status", {"status": status})
        statuses = tuple(valid_statuses if valid_statuses is not None else self.valid_statuses)
        if status not in statuses:
            return SafetyGateResult(False, "invalid task status", {"status": status, "valid": list(statuses)})
        return SafetyGateResult(True, None, {"status": status})

    def evaluate(
        self,
        *,
        task_id: str | None,
        changed_files: list[str] | tuple[str, ...] | None,
        evidence: dict[str, Any] | None,
        status: str | None,
        approved_tasks: tuple[str, ...] | None = None,
        allowed_files: tuple[str, ...] | None = None,
        valid_statuses: tuple[str, ...] | None = None,
    ) -> SafetyGateResult:
        task_scope = self.check_task_scope(task_id, approved_tasks=approved_tasks)
        if not task_scope.allowed:
            return task_scope

        modified = self.check_modified_files(changed_files, allowed_files=allowed_files)
        if not modified.allowed:
            return modified

        verification = self.check_verification_evidence(evidence)
        if not verification.allowed:
            return verification

        task_status = self.check_task_status(status, valid_statuses=valid_statuses)
        if not task_status.allowed:
            return task_status

        return SafetyGateResult(True, None, {
            "task_id": task_id,
            "changed_files": list(changed_files or []),
            "evidence": evidence,
            "status": status,
        })
