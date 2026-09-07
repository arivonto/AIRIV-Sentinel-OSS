from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import (
    DiagnosticAction,
    DiagnosticActionClassification,
    DiagnosticActionState,
    DiagnosticBudget,
    DiagnosticResult,
    Diagnosis,
    DiagnosisStatus,
    Hypothesis,
    HypothesisStatus,
    Investigation,
    InvestigationState,
    Observation,
)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported JSON value: {type(value)!r}")


def _write_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                default=_json_default,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class InvestigationStore:
    """
    Durable filesystem-backed store for Diagnostic Engine investigations.

    This store persists investigation state and diagnostic history.
    It does not own Incident lifecycle or remediation authority.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(
            root
            or os.environ.get(
                "AIRIV_SENTINEL_DIAGNOSTIC_DIR",
                "var/diagnostic",
            )
        )

    def _investigation_dir(self, investigation_id: str) -> Path:
        return self.root / "investigations" / investigation_id

    def save_investigation(self, investigation: Investigation) -> None:
        directory = self._investigation_dir(investigation.investigation_id)
        _write_atomic(directory / "investigation.json", investigation)

    def get_investigation(
        self,
        investigation_id: str,
    ) -> Investigation | None:
        path = self._investigation_dir(investigation_id) / "investigation.json"

        if not path.exists():
            return None

        data = _read_json(path)

        budget_data = data["budget"]

        budget = DiagnosticBudget(
            max_duration_seconds=budget_data["max_duration_seconds"],
            max_actions=budget_data["max_actions"],
            max_repeated_action=budget_data["max_repeated_action"],
            max_risk=budget_data["max_risk"],
            minimum_evidence=budget_data["minimum_evidence"],
            consumed_actions=budget_data.get("consumed_actions", 0),
            consumed_risk=budget_data.get("consumed_risk", 0),
            repeated_actions=budget_data.get("repeated_actions", {}),
        )

        return Investigation(
            investigation_id=data["investigation_id"],
            incident_id=data["incident_id"],
            component_id=data["component_id"],
            trigger=data["trigger"],
            state=InvestigationState(data["state"]),
            budget=budget,
            current_hypothesis_ids=data.get("current_hypothesis_ids", []),
            action_ids=data.get("action_ids", []),
            observation_ids=data.get("observation_ids", []),
            evidence_ids=data.get("evidence_ids", []),
            diagnosis_id=data.get("diagnosis_id"),
            created_at=_dt(data["created_at"]),
            updated_at=_dt(data["updated_at"]),
            completed_at=_dt(data.get("completed_at")),
        )

    def save_action(self, action: DiagnosticAction) -> None:
        directory = self._investigation_dir(action.investigation_id) / "actions"
        _write_atomic(
            directory / f"{action.diagnostic_action_id}.json",
            action,
        )

    def get_action(
        self,
        investigation_id: str,
        diagnostic_action_id: str,
    ) -> DiagnosticAction | None:
        path = (
            self._investigation_dir(investigation_id)
            / "actions"
            / f"{diagnostic_action_id}.json"
        )

        if not path.exists():
            return None

        data = _read_json(path)

        result = data.get("result")
        diagnostic_result = None

        if result is not None:
            diagnostic_result = DiagnosticResult(
                success=result["success"],
                stdout=result["stdout"],
                stderr=result["stderr"],
                exit_code=result["exit_code"],
                started_at=_dt(result["started_at"]),
                finished_at=_dt(result["finished_at"]),
                observation=result.get("observation", {}),
            )

        return DiagnosticAction(
            diagnostic_action_id=data["diagnostic_action_id"],
            investigation_id=data["investigation_id"],
            incident_id=data["incident_id"],
            classification=DiagnosticActionClassification(
                data["classification"]
            ),
            command=data["command"],
            rationale=data["rationale"],
            expected_information=data["expected_information"],
            state=DiagnosticActionState(data["state"]),
            result=diagnostic_result,
            started_at=_dt(data.get("started_at")),
            finished_at=_dt(data.get("finished_at")),
            evidence_ids=data.get("evidence_ids", []),
        )

    def save_observation(self, observation: Observation) -> None:
        directory = (
            self._investigation_dir(observation.investigation_id)
            / "observations"
        )
        _write_atomic(
            directory / f"{observation.observation_id}.json",
            asdict(observation),
        )

    def get_observation(self, investigation_id: str, observation_id: str) -> Observation | None:
        path = self._investigation_dir(investigation_id) / "observations" / f"{observation_id}.json"
        if not path.exists():
            return None
        data = _read_json(path)
        # Older writes serialized Observation.value alone; provenance cannot be recovered.
        if not isinstance(data, dict) or not {
            "observation_id", "investigation_id", "diagnostic_action_id",
            "component_id", "observed_at", "source", "subject", "value",
        }.issubset(data):
            return None
        data["observed_at"] = _dt(data["observed_at"])
        return Observation(**data)

    def get_hypothesis(self, investigation_id: str, hypothesis_id: str) -> Hypothesis | None:
        path = self._investigation_dir(investigation_id) / "hypotheses" / f"{hypothesis_id}.json"
        if not path.exists():
            return None
        data = _read_json(path)
        data["status"] = HypothesisStatus(data.get("status", "PROPOSED"))
        for key in ("created_at", "updated_at"):
            if key in data:
                data[key] = _dt(data[key])
        return Hypothesis(**data)

    def save_hypothesis(self, hypothesis: Hypothesis) -> None:
        directory = (
            self._investigation_dir(hypothesis.investigation_id)
            / "hypotheses"
        )
        _write_atomic(
            directory / f"{hypothesis.hypothesis_id}.json",
            hypothesis,
        )

    def save_diagnosis(self, diagnosis: Diagnosis) -> None:
        directory = self._investigation_dir(diagnosis.investigation_id)
        _write_atomic(
            directory / "diagnosis.json",
            diagnosis,
        )

    def append_history(
        self,
        investigation_id: str,
        event: dict[str, Any],
    ) -> None:
        directory = self._investigation_dir(investigation_id)
        directory.mkdir(parents=True, exist_ok=True)

        path = directory / "history.jsonl"
        line = json.dumps(
            event,
            default=_json_default,
            sort_keys=True,
        ) + "\n"

        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())

    def recover(self) -> list[Investigation]:
        investigations_root = self.root / "investigations"

        if not investigations_root.exists():
            return []

        recovered: list[Investigation] = []

        for directory in sorted(investigations_root.iterdir()):
            if not directory.is_dir():
                continue

            investigation_id = directory.name
            investigation = self.get_investigation(investigation_id)

            if investigation is not None:
                recovered.append(investigation)

        return recovered
