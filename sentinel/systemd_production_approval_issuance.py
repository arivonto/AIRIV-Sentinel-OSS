"""Inert trusted Commander approval to durable activation issuance (D8.14).

Only an authenticated upstream Commander adapter may supply the trusted input.
This module does not authenticate humans or decide approval.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from sentinel.resource_bound_remediation import ResourceBoundPermitBinding, BoundSystemdRemediationPlan
from sentinel.systemd_dispatch_evidence_binding import TrustedSystemdDispatchEvidenceBinding
from sentinel.systemd_evidence_plan_handoff import build_bound_systemd_plan_from_trusted_binding
from sentinel.systemd_production_activation import (
    SystemdProductionActivationGrant, _required_id, _finite_non_negative,
)
from sentinel.systemd_production_preparation import PreparedSystemdProductionRemediation
from sentinel.systemd_production_runtime_guard import _directory, _private


@dataclass(frozen=True, slots=True)
class TrustedSystemdProductionCommanderApproval:
    """Trusted in-process assertion, never a parser for untrusted approval text."""
    approval_id: str
    effect: ResourceBoundPermitBinding
    issued_at: float
    expires_at: float

    def __post_init__(self):
        _required_id(self.approval_id, 'approval_id')
        if type(self.effect) is not ResourceBoundPermitBinding:
            raise TypeError('canonical effect binding required')
        for name, value in self.effect.canonical_dict.items():
            if type(value) is not str or not value or value != value.strip() or '\x00' in value:
                raise ValueError('invalid approval effect identity')
            if name.endswith('fingerprint') and not re.fullmatch('[0-9a-f]{64}', value):
                raise ValueError('invalid approval fingerprint')
        issued = _finite_non_negative(self.issued_at, 'issued_at')
        expires = _finite_non_negative(self.expires_at, 'expires_at')
        if expires <= issued:
            raise ValueError('activation expiry must be after issuance')


def _json(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _filename(approval_id):
    return hashlib.sha256(approval_id.encode()).hexdigest() + '.json'


class SystemdProductionCommanderApprovalIssuer:
    """Approval-level single-use issuer; construction alone performs no I/O."""

    def __init__(self, root=None):
        default = Path.home() / '.local/state/airiv-sentinel-secure/systemd_production_approval_issuance'
        self.root = Path(os.path.abspath(os.path.expanduser(str(default if root is None else root))))

    def _records(self, directory):
        records = []
        for name in sorted(os.listdir(directory)):
            # Publication can rename staging entries after this snapshot.
            # Only the committed namespace (including reservations) is state.
            if name.startswith('.pending-'):
                continue
            if not re.fullmatch(r'[0-9a-f]{64}\.json', name):
                raise ValueError('malformed durable approval issuance')
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd) as handle:
                _private(os.fstat(handle.fileno()))
                raw = handle.read()
            try:
                payload = json.loads(raw)
                effect = ResourceBoundPermitBinding(**payload['effect'])
                approval = TrustedSystemdProductionCommanderApproval(
                    payload['approval_id'], effect, payload['issued_at'], payload['expires_at'])
                _required_id(payload['activation_id'], 'activation_id')
                expected = self._payload(approval, payload['activation_id'])
                if payload != expected or raw != _json(expected) or name != _filename(approval.approval_id):
                    raise ValueError('noncanonical record')
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('malformed durable approval issuance') from exc
            records.append(payload)
        return tuple(records)

    @staticmethod
    def _payload(approval, activation_id):
        return dict(schema_version=1, approval_id=approval.approval_id,
                    activation_id=activation_id, issued_at=float(approval.issued_at),
                    expires_at=float(approval.expires_at), effect=approval.effect.canonical_dict)

    def records(self):
        with _directory(self.root) as directory:
            return self._records(directory)

    def issue(self, *, approval, prepared, activation_id, now):
        if type(approval) is not TrustedSystemdProductionCommanderApproval:
            raise TypeError('trusted Commander approval required')
        approval.__post_init__()
        _required_id(activation_id, 'activation_id')
        current = _finite_non_negative(now, 'now')
        if not approval.issued_at <= current < approval.expires_at:
            raise ValueError('approval_not_active')
        if type(prepared) is not PreparedSystemdProductionRemediation:
            raise TypeError('canonical prepared effect required')
        if (type(prepared.plan) is not BoundSystemdRemediationPlan
                or type(prepared.binding) is not TrustedSystemdDispatchEvidenceBinding):
            raise TypeError('canonical prepared contents required')
        prepared_at = _finite_non_negative(prepared.prepared_at, 'prepared_at')
        if not prepared.binding.validated_at <= prepared_at <= current:
            raise ValueError('invalid preparation timestamp')
        plan = prepared.plan
        # Reuse canonical preparation continuity and freshness, without creating
        # a competing consumed-activation binding authority.
        expected = build_bound_systemd_plan_from_trusted_binding(
            binding=prepared.binding, now=current, privilege=plan.scope.privilege,
            run_id=plan.effect.run_id, execution_id=plan.effect.execution_id,
            permit_id=plan.effect.permit_id)
        if plan != expected or approval.effect != expected.permit_binding:
            raise ValueError('approval_prepared_binding_mismatch')
        payload = _json(self._payload(approval, activation_id))
        name = _filename(approval.approval_id)
        with _directory(self.root) as directory:
            self._records(directory)
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
            except FileExistsError as exc:
                raise ValueError('approval_already_issued') from exc
            try:
                _private(os.fstat(fd))
                os.fsync(fd)
                os.fsync(directory)
            finally:
                os.close(fd)
            # A crash retains the reservation. Partial/staging state blocks
            # subsequent issuance; never automatically reclaim an approval.
            temporary = '.pending-' + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            with os.fdopen(fd, 'w') as handle:
                _private(os.fstat(handle.fileno()))
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        # The sole grant construction path in this boundary is after durability.
        effect = approval.effect
        return SystemdProductionActivationGrant(
            activation_id=activation_id, approval_id=approval.approval_id,
            incident_id=effect.incident_id, component_id=effect.component_id,
            execution_id=effect.execution_id, effect_fingerprint=effect.effect_fingerprint,
            issued_at=approval.issued_at, expires_at=approval.expires_at)
