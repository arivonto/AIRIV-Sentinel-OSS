"""AIRIV Sentinel Contract Verification Boundary V1.

Boundary:
Normalized Observation -> Contract Verification -> Violation Evidence

This component detects and records violations only.
It MUST NOT execute remediation.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List


@dataclass(frozen=True)
class ContractViolation:
    """Immutable evidence describing one contract violation."""

    contract_id: str | None
    violation_type: str
    component_id: str
    reason: str
    detected_at: str
    observation: Dict[str, Any]


class ContractVerifier:
    """Deterministic verifier for canonical Sentinel observations."""

    # Observation integrity checks are implementation-level verification.
    # No canonical observation contract exists yet.
    CONTRACT_ID = None

    REQUIRED_FIELDS = (
        "source",
        "captured_at",
        "pane_id",
        "capture_ok",
        "pane_dead",
    )

    def verify(self, observation: Dict[str, Any]) -> List[ContractViolation]:
        if not isinstance(observation, dict):
            raise TypeError("observation must be a dictionary")

        violations: List[ContractViolation] = []
        component_id = str(observation.get("pane_id") or "")

        def add(violation_type: str, reason: str) -> None:
            violations.append(
                ContractViolation(
                    contract_id=self.CONTRACT_ID,
                    violation_type=violation_type,
                    component_id=component_id,
                    reason=reason,
                    detected_at=datetime.now(timezone.utc).isoformat(),
                    observation=dict(observation),
                )
            )

        # Structural integrity.
        for field in self.REQUIRED_FIELDS:
            if field not in observation:
                add(
                    "REQUIRED_FIELD_MISSING",
                    f"Required observation field missing: {field}",
                )

        if not component_id:
            add(
                "COMPONENT_ID_MISSING",
                "Canonical component identity requires observation.pane_id",
            )

        # Sensor capture contract.
        if observation.get("capture_ok") is False:
            add(
                "CAPTURE_FAILED",
                "Sensor observation reports capture_ok=false",
            )

        # A dead pane is an explicit observable violation condition.
        if observation.get("pane_dead") is True:
            add(
                "PANE_DEAD",
                "Observed tmux pane is dead",
            )

        return violations
