"""Durable attempt facts and concurrency only; no authorization or execution.

A partially written attempt is deliberately retained and fails closed on read.
The ledger is not execution/replay evidence and never records effect outcomes.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import math
import os
import re
from pathlib import Path
import stat

from sentinel.systemd_production_target_policy import (
    ACTION_RESTART, SystemdAttemptFact, validate_unit_name,
)


def _private(info, *, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not directory and info.st_nlink != 1)):
        raise ValueError("unsafe production state")


@contextmanager
def _directory(root, *, create=True):
    # Walk using directory descriptors: never follow a symlink component.
    if root == Path("/"):
        raise ValueError("production state cannot be filesystem root")
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for index, part in enumerate(root.parts[1:]):
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                    os.fsync(fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if index == len(root.parts) - 2:
                _private(info, directory=True)
            elif info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
                raise ValueError("unsafe production state ancestor")
        yield fd
    finally:
        os.close(fd)


def _root(root):
    configured = (
        root
        if root is not None
        else os.environ.get(
            'AIRIV_SENTINEL_SYSTEMD_PRODUCTION_STATE_DIR'
        )
    )

    if configured is None:
        configured = (
            Path.home()
            / '.local'
            / 'state'
            / 'airiv-sentinel-secure'
            / 'systemd_production_runtime'
        )

    return Path(os.path.abspath(os.path.expanduser(str(configured))))


@dataclass(frozen=True)
class SystemdProductionAttemptRecord:
    execution_id: str
    incident_id: str
    unit: str
    action: str
    timestamp: float
    target_fingerprint: str
    effect_fingerprint: str

    def __post_init__(self):
        for value in (self.execution_id, self.incident_id,
                      self.target_fingerprint, self.effect_fingerprint):
            if type(value) is not str or not value or value != value.strip():
                raise ValueError('invalid attempt binding')
        for value in (self.target_fingerprint, self.effect_fingerprint):
            if not re.fullmatch(r"[0-9a-f]{64}", value):
                raise ValueError('invalid attempt fingerprint')
        validate_unit_name(self.unit)
        if self.action != ACTION_RESTART:
            raise ValueError('invalid attempt action')
        if (type(self.timestamp) not in (int, float)
                or not math.isfinite(self.timestamp) or self.timestamp < 0):
            raise ValueError('invalid attempt timestamp')

    @classmethod
    def from_plan(cls, plan, timestamp):
        return cls(plan.effect.execution_id, plan.effect.incident_id,
                   plan.scope.target.unit_name, ACTION_RESTART, timestamp,
                   plan.effect.target_fingerprint, plan.effect.fingerprint)

    def to_fact(self):
        return SystemdAttemptFact(self.unit, self.action, self.timestamp)

    @property
    def filename(self):
        return hashlib.sha256(self.execution_id.encode()).hexdigest() + '.json'


class SystemdProductionAttemptLedger:
    def __init__(self, root=None):
        self.root = _root(root)

    def records(self):
        records = []
        with _directory(self.root) as directory:
            for name in sorted(os.listdir(directory)):
                if name == 'effect.lock':
                    continue
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
                with os.fdopen(fd) as handle:
                    _private(os.fstat(handle.fileno()))
                    payload = handle.read()
                try:
                    record = SystemdProductionAttemptRecord(**json.loads(payload))
                    canonical = json.dumps(asdict(record), sort_keys=True,
                                           separators=(',', ':'), allow_nan=False)
                    if name != record.filename or payload != canonical:
                        raise ValueError('noncanonical attempt')
                except (TypeError, ValueError) as exc:
                    raise ValueError('malformed durable production attempt') from exc
                records.append(record)
        return tuple(records)

    def attempts(self):
        return tuple(record.to_fact() for record in self.records())

    def append(self, record):
        if type(record) is not SystemdProductionAttemptRecord:
            raise TypeError('record must be SystemdProductionAttemptRecord')
        self.records()  # Never append past corrupt state.
        payload = json.dumps(asdict(record), sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
        with _directory(self.root) as directory:
            fd = os.open(record.filename,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=directory)
            # Publish the reservation durably before writing. A crash leaves
            # either a complete consumed attempt or a fail-closed partial one.
            try:
                os.fsync(directory)
                with os.fdopen(fd, 'w', closefd=False) as handle:
                    _private(os.fstat(fd))
                    handle.write(payload)
                    handle.flush()
                    os.fsync(fd)
                os.fsync(directory)
            finally:
                os.close(fd)


class SystemdProductionEffectLease:
    """Nonblocking kernel lease. Lock-file existence conveys no ownership."""
    def __init__(self, root=None):
        self.root = _root(root)
        self._fd = None

    def acquire(self):
        if self._fd is not None:
            raise RuntimeError('lease already acquired')
        with _directory(self.root) as directory:
            fd = os.open('effect.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                         | os.O_NONBLOCK, 0o600, dir_fd=directory)
            try:
                _private(os.fstat(fd))
                os.fsync(directory)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return False
            except BaseException:
                os.close(fd)
                raise
        self._fd = fd
        return True

    def close(self):
        if self._fd is not None:
            fd, self._fd = self._fd, None
            os.close(fd)


@contextmanager
def production_runtime_guard():
    ledger = SystemdProductionAttemptLedger()
    lease = SystemdProductionEffectLease(ledger.root)
    acquired = lease.acquire()
    try:
        # A contender must reach canonical policy with active=1; do not race
        # a writer by reading its unfinished durable reservation.
        yield ledger, acquired, ledger.attempts() if acquired else ()
    finally:
        lease.close()
