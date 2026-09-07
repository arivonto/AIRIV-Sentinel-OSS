"""Immutable pre-effect evidence supplied by trusted in-process collectors.

This boundary authenticates structure and durable integrity, not the truth of
caller-supplied observations. Only trusted collectors may append; a fingerprint
is not a signature. No incident strings are used to manufacture unit identity.
The general investigation store is mutable and loses typed snapshot identity;
this dedicated store reuses the production state's secure directory traversal.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

from sentinel.systemd_production_runtime_guard import _directory, _private
from sentinel.systemd_production_target_policy import validate_unit_name
from sentinel.systemd_remediation_safety import (
    SystemdManagerIdentity, SystemdUnitIdentity, SystemdUnitSnapshot,
)


def _text(value):
    if type(value) is not str or not value or value != value.strip() or '\x00' in value:
        raise ValueError('invalid evidence text')


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _snapshot(value):
    if (type(value) is not SystemdUnitSnapshot
            or type(value.identity) is not SystemdUnitIdentity
            or type(value.identity.manager) is not SystemdManagerIdentity):
        raise ValueError('canonical snapshot required')
    identity = value.identity
    manager = identity.manager
    validate_unit_name(identity.unit_name)
    for obj in (value, identity, manager):
        obj.__post_init__()
        for name, field in asdict(obj).items():
            if type(field) is str and name != 'invocation_id':
                _text(field)
    for number in (manager.manager_pid, manager.manager_start_ticks,
                   identity.fragment_device, identity.fragment_inode,
                   identity.fragment_uid, identity.fragment_gid,
                   value.main_pid, value.exec_main_start_timestamp_monotonic):
        if type(number) is not int:
            raise ValueError('exact integer facts required')
    if type(value.invocation_id) is not str:
        raise ValueError('invalid invocation id')
    if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', manager.boot_id):
        raise ValueError('invalid manager boot id')
    if str(Path(identity.fragment_path)) != identity.fragment_path or '..' in Path(identity.fragment_path).parts:
        raise ValueError('noncanonical fragment path')


@dataclass(frozen=True, slots=True)
class TrustedSystemdEvidenceRecord:
    incident_id: str
    component_id: str
    observation_id: str
    investigation_id: str
    observed_at: float
    snapshot: SystemdUnitSnapshot
    source: str = 'SYSTEMD'
    evidence_type: str = 'unit_snapshot'
    schema_version: int = 1

    def __post_init__(self):
        for value in (self.incident_id, self.component_id, self.observation_id,
                      self.investigation_id):
            _text(value)
        _snapshot(self.snapshot)
        if self.component_id != self.snapshot.identity.component_id:
            raise ValueError('component identity mismatch')
        if (type(self.schema_version) is not int or self.schema_version != 1
                or self.source != 'SYSTEMD' or self.evidence_type != 'unit_snapshot'):
            raise ValueError('unsupported evidence schema or source')
        if (type(self.observed_at) not in (int, float)
                or not math.isfinite(self.observed_at) or self.observed_at < 0):
            raise ValueError('invalid evidence timestamp')

    @property
    def fingerprint(self):
        return _digest(asdict(self))

    @property
    def evidence_id(self):
        return self.fingerprint

    def to_dict(self):
        self.__post_init__()
        return dict(asdict(self), fingerprint=self.fingerprint,
                    target_fingerprint=self.snapshot.identity.fingerprint,
                    manager_fingerprint=self.snapshot.identity.manager.fingerprint)

    @classmethod
    def from_dict(cls, payload):
        try:
            data = dict(payload)
            fingerprints = {key: data.pop(key) for key in (
                'fingerprint', 'target_fingerprint', 'manager_fingerprint')}
            snapshot = dict(data.pop('snapshot'))
            identity = dict(snapshot.pop('identity'))
            manager = SystemdManagerIdentity(**identity.pop('manager'))
            record = cls(snapshot=SystemdUnitSnapshot(
                identity=SystemdUnitIdentity(manager=manager, **identity), **snapshot), **data)
            if record.to_dict() != dict(payload) or any(
                    record.to_dict()[key] != value for key, value in fingerprints.items()):
                raise ValueError('fingerprint mismatch')
            return record
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise ValueError('malformed trusted systemd evidence') from exc


class TrustedSystemdEvidenceStore:
    def __init__(self, root=None):
        self.root = Path(os.path.abspath(root if root is not None else os.environ.get(
            'AIRIV_SENTINEL_SYSTEMD_EVIDENCE_DIR', 'var/systemd_evidence')))

    def _records(self, directory):
        result = []
        for name in sorted(os.listdir(directory)):
            # Unpublished atomic-write staging files convey no evidence.
            if re.fullmatch(r'\.pending-[0-9a-f]{32}', name):
                continue
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(fd) as handle:
                _private(os.fstat(handle.fileno()))
                payload = handle.read()
            record = TrustedSystemdEvidenceRecord.from_dict(json.loads(payload))
            if name != record.evidence_id + '.json' or payload != _json(record.to_dict()):
                raise ValueError('noncanonical durable evidence binding')
            result.append(record)
        return tuple(result)

    def records(self):
        try:
            with _directory(self.root, create=False) as directory:
                try:
                    return self._records(directory)
                except FileNotFoundError as exc:
                    raise ValueError('published evidence disappeared') from exc
        except FileNotFoundError:
            return ()

    def get(self, evidence_id):
        if type(evidence_id) is not str or not re.fullmatch('[0-9a-f]{64}', evidence_id):
            raise ValueError('invalid evidence id')
        return next((r for r in self.records() if r.evidence_id == evidence_id), None)

    def append(self, record):
        if type(record) is not TrustedSystemdEvidenceRecord:
            raise TypeError('trusted record required')
        payload = _json(record.to_dict())
        with _directory(self.root) as directory:
            self._records(directory)  # Never append past corrupt published evidence.
            temporary = '.pending-' + uuid.uuid4().hex
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'w') as handle:
                    _private(os.fstat(handle.fileno()))
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                # Hard-link publication is atomic and cannot replace an existing ID.
                os.link(temporary, record.evidence_id + '.json',
                        src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=directory)
                os.fsync(directory)
        return record.evidence_id
