"""Durable single-use production activation consumption.

Phase 2.13D.D8.10B.

The activation ID is the single-use namespace key.

Consumption uses an O_EXCL-created canonical file as the durable
one-winner reservation. The containing directory is fsynced before the
record body is written. Therefore a crash after reservation but before
a complete record deliberately leaves a malformed published record,
which causes future reads and consumption attempts to fail closed.

This boundary performs no policy evaluation, runtime activation,
delegation, execution, verification, or incident mutation.
"""

from dataclasses import (
    asdict,
    dataclass,
)
import hashlib
import json
import math
import os
from pathlib import Path
import re

from sentinel.systemd_production_activation import (
    SystemdProductionActivationBoundary,
    SystemdProductionActivationGrant,
)
from sentinel.systemd_production_runtime_guard import (
    _directory,
    _private,
)


_ACTIVATION_ID_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
)

_FINGERPRINT_RE = re.compile(
    r"[0-9a-f]{64}"
)


def _root(
    root,
):
    configured = (
        root
        if root is not None
        else os.environ.get(
            "AIRIV_SENTINEL_SYSTEMD_PRODUCTION_ACTIVATION_DIR"
        )
    )

    if configured is None:
        configured = (
            Path.home()
            / ".local"
            / "state"
            / "airiv-sentinel-secure"
            / "systemd_production_activation"
        )

    return Path(
        os.path.abspath(
            os.path.expanduser(
                str(
                    configured
                )
            )
        )
    )


def _required_text(
    value,
    name,
):
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or "\x00" in value
    ):
        raise ValueError(
            f"invalid {name}"
        )

    return value


def _timestamp(
    value,
):
    if (
        type(value) not in (
            int,
            float,
        )
        or not math.isfinite(
            value
        )
        or value < 0
    ):
        raise ValueError(
            "invalid activation consumption timestamp"
        )

    return float(
        value
    )


def _json(
    value,
):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        allow_nan=False,
    )


@dataclass(
    frozen=True,
    slots=True,
)
class SystemdProductionActivationConsumptionRecord:
    activation_id: str
    approval_id: str

    incident_id: str
    component_id: str
    execution_id: str
    effect_fingerprint: str

    grant_fingerprint: str
    consumed_at: float

    def __post_init__(
        self,
    ) -> None:
        if (
            type(self.activation_id)
            is not str
            or _ACTIVATION_ID_RE.fullmatch(
                self.activation_id
            )
            is None
        ):
            raise ValueError(
                "invalid activation id"
            )

        for name in (
            "approval_id",
            "incident_id",
            "component_id",
            "execution_id",
            "effect_fingerprint",
        ):
            _required_text(
                getattr(
                    self,
                    name,
                ),
                name,
            )

        if (
            type(self.grant_fingerprint)
            is not str
            or _FINGERPRINT_RE.fullmatch(
                self.grant_fingerprint
            )
            is None
        ):
            raise ValueError(
                "invalid grant fingerprint"
            )

        _timestamp(
            self.consumed_at
        )

    @classmethod
    def from_grant(
        cls,
        grant,
        consumed_at,
    ):
        if (
            type(grant)
            is not SystemdProductionActivationGrant
        ):
            raise TypeError(
                "SystemdProductionActivationGrant required"
            )

        return cls(
            activation_id=grant.activation_id,
            approval_id=grant.approval_id,
            incident_id=grant.incident_id,
            component_id=grant.component_id,
            execution_id=grant.execution_id,
            effect_fingerprint=(
                grant.effect_fingerprint
            ),
            grant_fingerprint=(
                grant.fingerprint
            ),
            consumed_at=_timestamp(
                consumed_at
            ),
        )

    @classmethod
    def from_dict(
        cls,
        payload,
    ):
        try:
            if type(payload) is not dict:
                raise ValueError(
                    "record object required"
                )

            record = cls(
                **payload
            )

            if record.to_dict() != payload:
                raise ValueError(
                    "noncanonical record"
                )

            return record

        except (
            TypeError,
            ValueError,
            KeyError,
        ) as exc:
            raise ValueError(
                "malformed activation consumption record"
            ) from exc

    def to_dict(
        self,
    ):
        self.__post_init__()

        return asdict(
            self
        )

    @property
    def filename(
        self,
    ):
        # Single-use is keyed by activation_id, not by mutable grant payload.
        return (
            hashlib.sha256(
                self.activation_id.encode(
                    "utf-8"
                )
            ).hexdigest()
            + ".json"
        )


class SystemdProductionActivationConsumptionStore:
    """Append-only durable single-use activation ledger."""

    def __init__(
        self,
        root=None,
        *,
        boundary=None,
    ):
        self.root = _root(
            root
        )

        self.boundary = (
            SystemdProductionActivationBoundary()
            if boundary is None
            else boundary
        )

        if (
            type(self.boundary)
            is not SystemdProductionActivationBoundary
        ):
            raise TypeError(
                "SystemdProductionActivationBoundary required"
            )

    def _records(
        self,
        directory,
    ):
        records = []

        for name in sorted(
            os.listdir(
                directory
            )
        ):
            try:
                fd = os.open(
                    name,
                    os.O_RDONLY
                    | os.O_NOFOLLOW
                    | os.O_NONBLOCK,
                    dir_fd=directory,
                )

                with os.fdopen(
                    fd,
                    "r",
                ) as handle:
                    _private(
                        os.fstat(
                            handle.fileno()
                        )
                    )

                    payload = handle.read()

                record = (
                    SystemdProductionActivationConsumptionRecord
                    .from_dict(
                        json.loads(
                            payload
                        )
                    )
                )

                canonical = _json(
                    record.to_dict()
                )

                if (
                    name
                    != record.filename
                    or payload
                    != canonical
                ):
                    raise ValueError(
                        "noncanonical durable activation consumption"
                    )

            except (
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "malformed durable activation consumption"
                ) from exc

            records.append(
                record
            )

        return tuple(
            records
        )

    def records(
        self,
    ):
        try:
            with _directory(
                self.root,
                create=False,
            ) as directory:
                try:
                    return self._records(
                        directory
                    )
                except FileNotFoundError as exc:
                    raise ValueError(
                        "published activation consumption disappeared"
                    ) from exc

        except FileNotFoundError:
            return ()

    def consumed(
        self,
        activation_id,
    ):
        if (
            type(activation_id)
            is not str
            or _ACTIVATION_ID_RE.fullmatch(
                activation_id
            )
            is None
        ):
            raise ValueError(
                "invalid activation id"
            )

        return any(
            record.activation_id
            == activation_id
            for record in self.records()
        )

    def consume(
        self,
        *,
        grant,
        now,
        incident_id,
        component_id,
        execution_id,
        effect_fingerprint,
    ):
        if (
            type(grant)
            is not SystemdProductionActivationGrant
        ):
            raise TypeError(
                "SystemdProductionActivationGrant required"
            )

        assessment = self.boundary.assess(
            grant=grant,
            now=now,
            incident_id=incident_id,
            component_id=component_id,
            execution_id=execution_id,
            effect_fingerprint=effect_fingerprint,
        )

        if not assessment.eligible:
            raise ValueError(
                assessment.reason
            )

        record = (
            SystemdProductionActivationConsumptionRecord
            .from_grant(
                grant,
                now,
            )
        )

        # Never write past any malformed durable state.
        existing = self.records()

        if any(
            prior.activation_id
            == record.activation_id
            for prior in existing
        ):
            raise ValueError(
                "activation_already_consumed"
            )

        payload = _json(
            record.to_dict()
        )

        with _directory(
            self.root
        ) as directory:
            # Re-read under the secure directory immediately before claim.
            self._records(
                directory
            )

            try:
                fd = os.open(
                    record.filename,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=directory,
                )

            except FileExistsError as exc:
                raise ValueError(
                    "activation_already_consumed"
                ) from exc

            # Durable reservation first.
            #
            # A crash from this point onward consumes the activation
            # conservatively. A partial file is intentionally not ignored.
            try:
                os.fsync(
                    directory
                )

                with os.fdopen(
                    fd,
                    "w",
                    closefd=False,
                ) as handle:
                    _private(
                        os.fstat(
                            fd
                        )
                    )

                    handle.write(
                        payload
                    )

                    handle.flush()

                    os.fsync(
                        fd
                    )

                os.fsync(
                    directory
                )

            finally:
                os.close(
                    fd
                )

        return record
