"""Scheduling entry boundary; OperationalDaemon owns the periodic loop."""

from .daemon import DaemonSnapshot, OperationalDaemon


class RuntimeScheduler:
    def __init__(self, daemon: OperationalDaemon) -> None:
        if not isinstance(daemon, OperationalDaemon):
            raise TypeError("daemon must be OperationalDaemon")
        self._daemon = daemon

    def run_forever(self) -> None:
        self._daemon.run_forever()

    def request_stop(self) -> None:
        self._daemon.request_stop()

    def snapshot(self) -> DaemonSnapshot:
        return self._daemon.snapshot()
