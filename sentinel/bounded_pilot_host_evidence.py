"""Side-effect-free host evidence projection for the bounded pilot.

This module normalizes caller-supplied host facts into the existing bounded
pilot verification gate. It never queries systemd, reads journals, restarts
services, or mutates host state.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from sentinel.bounded_pilot_readiness import (
    PILOT_UNIT,
    BoundedPilotVerificationFacts,
)


@dataclass(frozen=True, slots=True)
class BoundedPilotHostEvidence:
    unit: str
    active_state: str
    sub_state: str
    main_pid: int
    runtime_identity: str
    expected_runtime_identity: str
    journal_unit: str
    journal_boot_id: str
    journal_after_activation: bool
    evidence_path_validated: bool
    observed_at: float
    activation_observed_at: float

    def __post_init__(self) -> None:
        for name in (
            "unit",
            "active_state",
            "sub_state",
            "runtime_identity",
            "expected_runtime_identity",
            "journal_unit",
            "journal_boot_id",
        ):
            _bounded_text(getattr(self, name), name)
        if type(self.main_pid) is not int:
            raise ValueError("main_pid must be exact integer")
        if type(self.journal_after_activation) is not bool:
            raise ValueError("journal_after_activation must be bool")
        if type(self.evidence_path_validated) is not bool:
            raise ValueError("evidence_path_validated must be bool")
        _finite_non_negative(self.observed_at, "observed_at")
        _finite_non_negative(
            self.activation_observed_at,
            "activation_observed_at",
        )


@dataclass(frozen=True, slots=True)
class BoundedPilotHostEvidenceProjection:
    verification: BoundedPilotVerificationFacts
    reasons: tuple[str, ...]

    @property
    def verified(self) -> bool:
        return self.reasons == ("bounded_pilot_host_evidence_verified",)


def project_bounded_pilot_host_evidence(
    evidence: BoundedPilotHostEvidence,
) -> BoundedPilotHostEvidenceProjection:
    """Project detached host facts into bounded pilot verification facts."""

    if type(evidence) is not BoundedPilotHostEvidence:
        raise TypeError("BoundedPilotHostEvidence required")

    unit_exact = evidence.unit == PILOT_UNIT
    journal_unit_exact = evidence.journal_unit == PILOT_UNIT
    pid_check = unit_exact and evidence.main_pid > 0
    active_state_check = (
        unit_exact
        and evidence.active_state == "active"
        and evidence.sub_state == "running"
    )
    runtime_identity_check = (
        unit_exact
        and evidence.runtime_identity == evidence.expected_runtime_identity
    )
    journal_continuity_check = (
        journal_unit_exact
        and bool(evidence.journal_boot_id)
        and evidence.journal_after_activation
        and evidence.observed_at >= evidence.activation_observed_at
    )

    verification = BoundedPilotVerificationFacts(
        pid_check=pid_check,
        active_state_check=active_state_check,
        runtime_identity_check=runtime_identity_check,
        journal_continuity_check=journal_continuity_check,
        evidence_path_validated=evidence.evidence_path_validated,
    )

    reasons: list[str] = []
    if not unit_exact:
        reasons.append("host_unit_mismatch")
    if evidence.main_pid <= 0:
        reasons.append("host_pid_missing")
    if not active_state_check:
        reasons.append("host_not_active_running")
    if not runtime_identity_check:
        reasons.append("host_runtime_identity_mismatch")
    if not journal_unit_exact:
        reasons.append("journal_unit_mismatch")
    if not evidence.journal_boot_id:
        reasons.append("journal_boot_id_missing")
    if not evidence.journal_after_activation:
        reasons.append("journal_after_activation_missing")
    if evidence.observed_at < evidence.activation_observed_at:
        reasons.append("host_evidence_precedes_activation")
    if not evidence.evidence_path_validated:
        reasons.append("host_evidence_path_not_validated")

    return BoundedPilotHostEvidenceProjection(
        verification=verification,
        reasons=tuple(reasons) or (
            "bounded_pilot_host_evidence_verified",
        ),
    )


def _bounded_text(value: str, name: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise ValueError(f"{name} must be bounded text")


def _finite_non_negative(value: float, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return float(value)
