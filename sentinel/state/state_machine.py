import time
from dataclasses import dataclass
from typing import Dict, Optional


class JobProfile:
    """
    Canonical workload profiles.

    Silence is an anomaly signal only.
    Silence does not independently prove STUCK.
    """

    THRESHOLDS = {
        "DEFAULT": 60,
        "PYTEST": 180,
        "DOCKER_BUILD": 300,
        "MIGRATION": 120,
        "LLM_INFERENCE": 90,
    }

    @classmethod
    def get_threshold(cls, job_type: str) -> int:
        return cls.THRESHOLDS.get(
            (job_type or "DEFAULT").upper(),
            cls.THRESHOLDS["DEFAULT"],
        )


class JobClassifier:
    """
    Deterministic workload classifier.

    Classification is based only on observable command metadata.
    No semantic inference or LLM reasoning is performed here.
    """

    RULES = (
        ("PYTEST", ("pytest", "py.test")),
        ("DOCKER_BUILD", ("docker build", "docker compose build")),
        ("MIGRATION", ("alembic upgrade", "alembic revision")),
        ("LLM_INFERENCE", ("ollama",)),
    )

    @classmethod
    def classify(cls, observation: Dict) -> str:
        command = (
            observation.get("current_command")
            or ""
        ).strip().lower()

        for job_type, patterns in cls.RULES:
            if any(pattern in command for pattern in patterns):
                return job_type

        return "DEFAULT"


@dataclass
class StateEvidence:
    """
    Evidence retained for deterministic state evaluation.
    """

    last_activity_at: float
    last_output_hash: Optional[str]
    job_type: str


class StateMachine:
    """
    Deterministic lifecycle state machine.

    Lifecycle:

        IDLE
          ↓
        OBSERVING
          ↓
        TASK_ACTIVE
          ├── WAITING
          ├── STUCK
          └── COMPLETED

    Important:
        OUTPUT_SILENT alone does not imply STUCK.
        COMPLETED requires explicit completion evidence.
    """

    VALID_STATES = {
        "IDLE",
        "OBSERVING",
        "TASK_ACTIVE",
        "WAITING",
        "STUCK",
        "COMPLETED",
        "FAILED",
    }

    def __init__(
        self,
        component_id: str,
        default_job_type: str = "DEFAULT",
    ):
        self.component_id = component_id
        self.state = "IDLE"

        self.evidence = StateEvidence(
            last_activity_at=time.monotonic(),
            last_output_hash=None,
            job_type=(
                default_job_type or "DEFAULT"
            ).upper(),
        )

    @property
    def current_job_type(self) -> str:
        return self.evidence.job_type

    def set_job_type(self, job_type: str) -> None:
        self.evidence.job_type = (
            job_type or "DEFAULT"
        ).upper()

    def _record_activity(
        self,
        observation: Dict,
    ) -> None:
        self.evidence.last_activity_at = time.monotonic()

        output_hash = observation.get(
            "output_sha256"
        )

        if output_hash:
            self.evidence.last_output_hash = output_hash

    @staticmethod
    def _has_completion_evidence(
        observation: Dict,
    ) -> bool:
        """
        Completion must be explicit.

        The normalizer does not invent completion semantics.
        Upstream components may provide explicit completion evidence.
        """

        return (
            observation.get("completion_evidence")
            is True
        )

    @staticmethod
    def _has_waiting_evidence(
        observation: Dict,
    ) -> bool:
        """
        Waiting requires explicit lifecycle evidence.
        """

        return (
            observation.get("waiting_evidence")
            is True
        )

    def update_state(
        self,
        observation: Dict,
    ) -> str:

        activity_state = observation.get(
            "activity_state"
        )

        output_changed = observation.get(
            "output_changed",
            False,
        )

        # ----------------------------------------------------------
        # Hard liveness failure
        # ----------------------------------------------------------

        if activity_state == "PANE_DEAD":
            self.state = "FAILED"
            return self.state

        # ----------------------------------------------------------
        # Explicit completion evidence
        # ----------------------------------------------------------

        if self._has_completion_evidence(observation):
            self.state = "COMPLETED"
            return self.state

        # ----------------------------------------------------------
        # Capture failure is an observability condition.
        # It does not itself prove WAITING.
        # ----------------------------------------------------------

        if activity_state == "CAPTURE_FAILED":
            return self.state

        # ----------------------------------------------------------
        # First observation
        # ----------------------------------------------------------

        if activity_state == "INITIALIZED":
            if self.state == "IDLE":
                self.state = "OBSERVING"

            return self.state

        # ----------------------------------------------------------
        # Explicit activity/progress
        # ----------------------------------------------------------

        active_events = {
            "PROCESS_CHANGED",
            "OUTPUT_CHANGED",
        }

        if (
            output_changed
            or activity_state in active_events
        ):
            self._record_activity(observation)

            if self.state in {
                "IDLE",
                "OBSERVING",
                "WAITING",
                "STUCK",
            }:
                self.state = "TASK_ACTIVE"

            return self.state

        # ----------------------------------------------------------
        # Explicit waiting evidence
        # ----------------------------------------------------------

        if self._has_waiting_evidence(observation):
            if self.state == "TASK_ACTIVE":
                self.state = "WAITING"

            return self.state

        # ----------------------------------------------------------
        # Silence evaluation
        # ----------------------------------------------------------

        if activity_state == "OUTPUT_SILENT":
            elapsed = (
                time.monotonic()
                - self.evidence.last_activity_at
            )

            threshold = JobProfile.get_threshold(
                self.current_job_type
            )

            # Silence is only meaningful once a task is known
            # to be active.
            if (
                self.state == "TASK_ACTIVE"
                and elapsed > threshold
            ):
                self.state = "STUCK"

        return self.state


def classify_and_update(
    state_machine: StateMachine,
    observation: Dict,
) -> str:
    """
    Convenience boundary:

        normalized observation
            -> job classification
            -> state evaluation
    """

    classified_job = JobClassifier.classify(
        observation
    )

    state_machine.set_job_type(
        classified_job
    )

    return state_machine.update_state(
        observation
    )
