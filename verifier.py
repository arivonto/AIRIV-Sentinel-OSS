from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class VerificationEvidence:
    status: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "details": self.details}


class Verifier:
    """Deterministic verifier for task execution evidence and bounded scope."""

    def __init__(self, *, allowed_files: tuple[str, ...] = ()) -> None:
        self.allowed_files = tuple(allowed_files)

    def verify_task(
        self,
        *,
        task: dict[str, Any] | None = None,
        success_condition: str | None = None,
        changed_files: list[str] | tuple[str, ...] | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> VerificationEvidence:
        if task is None:
            return VerificationEvidence("FAIL", {"reason": "task is required"})
        if success_condition is None:
            return VerificationEvidence("FAIL", {"reason": "success condition is required"})

        changed = list(changed_files or [])
        scope_result = self.verify_scope(changed_files=changed)
        if scope_result.status == "FAIL":
            return scope_result

        success_result = self.verify_success(
            task=task,
            success_condition=success_condition,
            evidence=evidence or {},
        )
        if success_result.status == "FAIL":
            return success_result

        return VerificationEvidence(
            "PASS",
            {
                "task_id": task.get("id"),
                "task_name": task.get("name"),
                "changed_files": changed,
                "success_condition": success_condition,
                "evidence": evidence or {},
            },
        )

    def verify_success(
        self,
        *,
        task: dict[str, Any] | None = None,
        success_condition: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> VerificationEvidence:
        if task is None:
            return VerificationEvidence("FAIL", {"reason": "task is required"})
        if success_condition is None:
            return VerificationEvidence("FAIL", {"reason": "success condition is required"})
        if evidence is None:
            evidence = {}

        condition = str(success_condition).strip()
        if not condition:
            return VerificationEvidence("FAIL", {"reason": "success condition is empty"})

        evidence_text = str(evidence)
        if condition not in evidence_text:
            return VerificationEvidence(
                "FAIL",
                {
                    "reason": "success condition missing from evidence",
                    "required": condition,
                    "evidence": evidence,
                },
            )

        return VerificationEvidence("PASS", {"required": condition, "evidence": evidence})

    def verify_changed_files(
        self,
        *,
        changed_files: list[str] | tuple[str, ...] | None = None,
    ) -> VerificationEvidence:
        changed = list(changed_files or [])
        if not changed:
            return VerificationEvidence("FAIL", {"reason": "no changed files were supplied"})
        return VerificationEvidence("PASS", {"changed_files": changed})

    def verify_scope(
        self,
        *,
        changed_files: list[str] | tuple[str, ...] | None = None,
        allowed_files: tuple[str, ...] | None = None,
    ) -> VerificationEvidence:
        scoped_files = list(changed_files or [])
        allowed = tuple(allowed_files if allowed_files is not None else self.allowed_files)
        if not allowed:
            return VerificationEvidence("PASS", {"changed_files": scoped_files})

        unexpected = [path for path in scoped_files if path not in allowed]
        if unexpected:
            return VerificationEvidence(
                "FAIL",
                {
                    "reason": "unexpected modified files",
                    "unexpected": unexpected,
                    "allowed": list(allowed),
                },
            )
        return VerificationEvidence("PASS", {"changed_files": scoped_files})

    def verify_result(
        self,
        *,
        task: dict[str, Any] | None = None,
        success_condition: str | None = None,
        changed_files: list[str] | tuple[str, ...] | None = None,
        evidence: dict[str, Any] | None = None,
        allowed_files: tuple[str, ...] | None = None,
    ) -> VerificationEvidence:
        scope_result = self.verify_scope(
            changed_files=changed_files,
            allowed_files=allowed_files,
        )
        if scope_result.status == "FAIL":
            return scope_result

        success_result = self.verify_success(
            task=task,
            success_condition=success_condition,
            evidence=evidence or {},
        )
        if success_result.status == "FAIL":
            return success_result

        return VerificationEvidence(
            "PASS",
            {
                "task": task,
                "success_condition": success_condition,
                "changed_files": list(changed_files or []),
                "evidence": evidence or {},
            },
        )
