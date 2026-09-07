"""Live-remediation safety primitives.

These types do not authorize, execute, verify, or mutate incidents.
They only provide immutable identity and effect-binding values used by
the existing canonical authorities.
"""

from __future__ import annotations

from sentinel.bound_effect_contract import BoundRemediationEffectContract


from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


@dataclass(frozen=True)
class TmuxTargetIdentity:
    run_id: str
    server_socket: str
    session_id: str
    session_name: str
    window_id: str
    pane_id: str
    server_generation: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "server_socket",
            "session_id",
            "session_name",
            "window_id",
            "pane_id",
        ):
            object.__setattr__(
                self,
                name,
                _required(getattr(self, name), name),
            )

        if self.server_generation is not None:
            object.__setattr__(
                self,
                "server_generation",
                _required(self.server_generation, "server_generation"),
            )

    def canonical_dict(self) -> dict[str, str | None]:
        return {
            "run_id": self.run_id,
            "server_socket": self.server_socket,
            "server_generation": self.server_generation,
            "session_id": self.session_id,
            "session_name": self.session_name,
            "window_id": self.window_id,
            "pane_id": self.pane_id,
        }

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.canonical_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @property
    def live_eligible(self) -> bool:
        # Server generation is mandatory for eventual live execution.
        return self.server_generation is not None

    # PHASE_213C1C_FROM_OBSERVATION
    @classmethod
    def from_observation(cls, observation, *, run_id: str):
        from collections.abc import Mapping

        if not isinstance(observation, Mapping):
            raise TypeError("observation must be a mapping")

        if observation.get("source") != "TMUX":
            raise ValueError("strong target requires TMUX observation")

        if observation.get("tmux_identity_valid") is not True:
            raise ValueError("TMUX observation identity is not strong")

        captured_at = observation.get("captured_at")
        if not isinstance(captured_at, str) or not captured_at.strip():
            raise ValueError("captured_at provenance is required")

        output_sha256 = observation.get("output_sha256")
        if not isinstance(output_sha256, str) or len(output_sha256) != 64:
            raise ValueError("output_sha256 provenance is required")

        try:
            int(output_sha256, 16)
        except ValueError as exc:
            raise ValueError("output_sha256 must be hexadecimal") from exc

        identity = observation.get("tmux_identity")

        if identity is not None:
            if not isinstance(identity, Mapping):
                raise ValueError("tmux_identity must be a mapping")

            for key in (
                "server_socket",
                "server_generation",
                "session_id",
                "session_name",
                "window_id",
                "pane_id",
            ):
                if identity.get(key) != observation.get(key):
                    raise ValueError("tmux_identity_snapshot_mismatch")

        return cls(
            run_id=_required(run_id, "run_id"),
            server_socket=_required(
                observation.get("server_socket"),
                "server_socket",
            ),
            session_id=_required(
                observation.get("session_id"),
                "session_id",
            ),
            session_name=_required(
                observation.get("session_name"),
                "session_name",
            ),
            window_id=_required(
                observation.get("window_id"),
                "window_id",
            ),
            pane_id=_required(
                observation.get("pane_id"),
                "pane_id",
            ),
            server_generation=_required(
                observation.get("server_generation"),
                "server_generation",
            ),
        )

    @classmethod
    def from_evidence(cls, raw_evidence, *, run_id: str):
        import json
        from collections.abc import Mapping

        if isinstance(raw_evidence, Mapping):
            observation = dict(raw_evidence)

        elif isinstance(raw_evidence, str):
            try:
                observation = json.loads(raw_evidence)
            except json.JSONDecodeError as exc:
                raise ValueError("raw_evidence is not valid JSON") from exc

            if not isinstance(observation, Mapping):
                raise ValueError("raw_evidence JSON must contain an object")

        else:
            raise TypeError(
                "raw_evidence must be mapping or JSON string"
            )

        return cls.from_observation(
            observation,
            run_id=run_id,
        )


@dataclass(frozen=True)
class BoundRemediationEffect(BoundRemediationEffectContract):

    @property
    def policy_run_id(self) -> str:
        """Canonical policy run key; preserves legacy TMUX semantics."""
        return self.target.run_id

    incident_id: str
    component_id: str
    action: str
    argv: tuple[str, ...]
    target: TmuxTargetIdentity
    execution_id: str
    permit_id: str

    def __post_init__(self) -> None:
        for name in (
            "incident_id",
            "component_id",
            "action",
            "execution_id",
            "permit_id",
        ):
            object.__setattr__(
                self,
                name,
                _required(getattr(self, name), name),
            )

        argv = tuple(self.argv)

        if not argv:
            raise ValueError("argv must not be empty")

        if any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("argv entries must be non-empty strings")

        object.__setattr__(self, "argv", argv)

        if self.component_id != self.target.pane_id:
            raise ValueError("component_target_mismatch")

    @property
    def fingerprint(self) -> str:
        payload = {
            "incident_id": self.incident_id,
            "component_id": self.component_id,
            "action": self.action,
            "argv": list(self.argv),
            "target": self.target.canonical_dict(),
            "execution_id": self.execution_id,
            "permit_id": self.permit_id,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(encoded.encode("utf-8")).hexdigest()

    def matches(
        self,
        *,
        incident_id: str,
        component_id: str,
        action: str,
        argv: Iterable[str],
        target: TmuxTargetIdentity,
        execution_id: str,
        permit_id: str,
    ) -> bool:
        candidate = BoundRemediationEffect(
            incident_id=incident_id,
            component_id=component_id,
            action=action,
            argv=tuple(argv),
            target=target,
            execution_id=execution_id,
            permit_id=permit_id,
        )
        return candidate == self


@dataclass(frozen=True)
class BoundRemediationAuthorization:
    """Immutable result of RemediationPolicy bound-effect evaluation.

    This DTO is not a second authorization authority. RemediationPolicy
    remains the sole owner of ALLOW/DENY.
    """

    decision: str
    reason: str
    incident_id: str
    component_id: str
    action: str
    run_id: str
    execution_id: str
    permit_id: str
    target_fingerprint: str
    effect_fingerprint: str

    def __post_init__(self) -> None:
        if self.decision not in {"ALLOW", "DENY"}:
            raise ValueError("decision must be ALLOW or DENY")

        for name in (
            "reason",
            "incident_id",
            "component_id",
            "action",
            "run_id",
            "execution_id",
            "permit_id",
            "target_fingerprint",
            "effect_fingerprint",
        ):
            object.__setattr__(
                self,
                name,
                _required(getattr(self, name), name),
            )

    @property
    def authorized(self) -> bool:
        return self.decision == "ALLOW"

    @property
    def fingerprint(self) -> str:
        payload = {
            "decision": self.decision,
            "reason": self.reason,
            "incident_id": self.incident_id,
            "component_id": self.component_id,
            "action": self.action,
            "run_id": self.run_id,
            "execution_id": self.execution_id,
            "permit_id": self.permit_id,
            "target_fingerprint": self.target_fingerprint,
            "effect_fingerprint": self.effect_fingerprint,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(encoded.encode("utf-8")).hexdigest()

    def matches(self, effect) -> bool:
        from sentinel.bound_effect_contract import (
            bound_effect_policy_run_id,
            bound_effect_target_fingerprint,
            validate_bound_effect_contract,
        )

        try:
            validate_bound_effect_contract(
                effect
            )

            run_id = (
                bound_effect_policy_run_id(
                    effect
                )
            )

            target_fingerprint = (
                bound_effect_target_fingerprint(
                    effect
                )
            )

        except (
            TypeError,
            ValueError,
            AttributeError,
            NotImplementedError,
        ):
            return False

        return (
            self.incident_id == effect.incident_id
            and self.component_id == effect.component_id
            and self.action == effect.action
            and self.run_id == run_id
            and self.execution_id == effect.execution_id
            and self.permit_id == effect.permit_id
            and self.target_fingerprint == target_fingerprint
            and self.effect_fingerprint == effect.fingerprint
        )


@dataclass(frozen=True)
class LiveRunPermitRecord:
    """Durable single-run permit identity owned by execution identity journal."""

    run_id: str
    permit_id: str
    execution_id: str
    incident_id: str
    component_id: str
    action: str
    target_fingerprint: str
    effect_fingerprint: str
    authorization_fingerprint: str
    state: str = "CLAIMED"

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "permit_id",
            "execution_id",
            "incident_id",
            "component_id",
            "action",
            "target_fingerprint",
            "effect_fingerprint",
            "authorization_fingerprint",
            "state",
        ):
            object.__setattr__(
                self,
                name,
                _required(getattr(self, name), name),
            )

        if self.state != "CLAIMED":
            raise ValueError("live run permit state must be CLAIMED")

    def canonical_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "permit_id": self.permit_id,
            "execution_id": self.execution_id,
            "incident_id": self.incident_id,
            "component_id": self.component_id,
            "action": self.action,
            "target_fingerprint": self.target_fingerprint,
            "effect_fingerprint": self.effect_fingerprint,
            "authorization_fingerprint": self.authorization_fingerprint,
            "state": self.state,
        }


@dataclass(frozen=True)
class LiveRunPermitClaim:
    record: LiveRunPermitRecord
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.record, LiveRunPermitRecord):
            raise TypeError("record must be a LiveRunPermitRecord")

        if type(self.replayed) is not bool:
            raise TypeError("replayed must be bool")
