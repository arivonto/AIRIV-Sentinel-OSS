"""Bound live-remediation composition.

This module constructs immutable remediation and verification DTOs from
one proven TMUX observation.

It does not:
    - evaluate policy
    - authorize remediation
    - claim execution identity
    - claim a run permit
    - execute commands
    - mutate Incident lifecycle
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sentinel.live_remediation_safety import (
    BoundRemediationEffect,
    TmuxTargetIdentity,
)
from sentinel.tmux_remediation_verifier import (
    TmuxVerificationTarget,
)


def _nonempty(
    value: str,
    field: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"{field} must be str"
        )

    value = value.strip()

    if not value:
        raise ValueError(
            f"{field} is required"
        )

    return value


def _mapping_from_evidence(
    raw_evidence: Mapping[str, Any] | str,
) -> dict[str, Any]:
    if isinstance(
        raw_evidence,
        Mapping,
    ):
        return dict(raw_evidence)

    if isinstance(
        raw_evidence,
        str,
    ):
        try:
            value = json.loads(
                raw_evidence
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "raw_evidence is not valid JSON"
            ) from exc

        if not isinstance(
            value,
            Mapping,
        ):
            raise ValueError(
                "raw_evidence JSON must contain object"
            )

        return dict(value)

    raise TypeError(
        "raw_evidence must be mapping or JSON string"
    )


def _target_fingerprint(
    target: TmuxTargetIdentity,
) -> str:
    value = getattr(
        target,
        "fingerprint",
        None,
    )

    if value is None:
        raise RuntimeError(
            "TmuxTargetIdentity has no fingerprint"
        )

    if callable(value):
        value = value()

    if not isinstance(value, str) or not value:
        raise RuntimeError(
            "invalid TMUX target fingerprint"
        )

    return value


@dataclass(
    frozen=True,
    slots=True,
)
class BoundTmuxRemediationPlan:
    """Immutable pre-effect plan.

    ``target`` is the canonical target authority for both the effect and
    verification target.
    """

    target: TmuxTargetIdentity
    effect: BoundRemediationEffect
    verification_target: TmuxVerificationTarget

    captured_at: str
    output_sha256: str
    target_fingerprint: str

    def __post_init__(self) -> None:
        if self.effect.target != self.target:
            raise ValueError(
                "effect_target_mismatch"
            )

        if (
            self.verification_target.identity
            != self.target
        ):
            raise ValueError(
                "verification_target_mismatch"
            )

        if (
            self.effect.component_id
            != self.target.pane_id
        ):
            raise ValueError(
                "component_target_mismatch"
            )

        if (
            self.verification_target.pane_id
            != self.target.pane_id
        ):
            raise ValueError(
                "verification_pane_mismatch"
            )

        if (
            self.verification_target.strong_identity
            is not True
        ):
            raise ValueError(
                "strong_verification_required"
            )

        if (
            _target_fingerprint(
                self.target
            )
            != self.target_fingerprint
        ):
            raise ValueError(
                "target_fingerprint_mismatch"
            )


def build_bound_tmux_remediation_plan(
    *,
    raw_evidence: Mapping[str, Any] | str,
    run_id: str,
    incident_id: str,
    component_id: str,
    action: str,
    argv: Sequence[str],
    execution_id: str,
    permit_id: str,
    expected_alive: bool = True,
    timeout: float = 5.0,
) -> BoundTmuxRemediationPlan:
    """Construct effect + verifier target from one proven observation."""

    evidence = _mapping_from_evidence(
        raw_evidence
    )

    target = (
        TmuxTargetIdentity
        .from_evidence(
            evidence,
            run_id=_nonempty(
                run_id,
                "run_id",
            ),
        )
    )

    component_id = _nonempty(
        component_id,
        "component_id",
    )

    if component_id != target.pane_id:
        raise ValueError(
            "component_target_mismatch"
        )

    if (
        not isinstance(argv, Sequence)
        or isinstance(
            argv,
            (str, bytes),
        )
    ):
        raise TypeError(
            "argv must be a sequence of strings"
        )

    immutable_argv = tuple(argv)

    if (
        not immutable_argv
        or any(
            not isinstance(item, str)
            or not item
            for item in immutable_argv
        )
    ):
        raise ValueError(
            "argv must contain non-empty strings"
        )

    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
    ):
        raise ValueError(
            "timeout must be positive"
        )

    captured_at = evidence.get(
        "captured_at"
    )

    output_sha256 = evidence.get(
        "output_sha256"
    )

    if (
        not isinstance(captured_at, str)
        or not captured_at
    ):
        raise ValueError(
            "captured_at provenance required"
        )

    if (
        not isinstance(output_sha256, str)
        or len(output_sha256) != 64
    ):
        raise ValueError(
            "output_sha256 provenance required"
        )

    effect = BoundRemediationEffect(
        incident_id=_nonempty(
            incident_id,
            "incident_id",
        ),
        component_id=component_id,
        action=_nonempty(
            action,
            "action",
        ),
        argv=immutable_argv,
        target=target,
        execution_id=_nonempty(
            execution_id,
            "execution_id",
        ),
        permit_id=_nonempty(
            permit_id,
            "permit_id",
        ),
    )

    verification_target = (
        TmuxVerificationTarget(
            pane_id=target.pane_id,
            expected_alive=expected_alive,
            identity=target,
            timeout=float(timeout),
            strong_identity=True,
        )
    )

    return BoundTmuxRemediationPlan(
        target=target,
        effect=effect,
        verification_target=verification_target,
        captured_at=captured_at,
        output_sha256=output_sha256,
        target_fingerprint=(
            _target_fingerprint(target)
        ),
    )
