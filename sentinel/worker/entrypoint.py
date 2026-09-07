"""Foreground production process lifecycle; scheduling belongs to the daemon."""

from collections.abc import Sequence
from contextlib import ExitStack
import logging
import signal

from sentinel.runtime import SentinelRuntime

from .composition import (
    RuntimeSupervisionConfig,
    build_production_supervision as build_runtime_supervision,
)
from .models import WorkerId
from .scheduler import RuntimeScheduler
from .supervisor import RestartPolicy


logger = logging.getLogger(__name__)


def build_production_runtime() -> SentinelRuntime:
    """Construct the canonical runtime graph exactly once, without starting it."""
    return SentinelRuntime()


def build_production_config() -> RuntimeSupervisionConfig:
    """Explicit process defaults, using the existing immutable config contract."""
    return RuntimeSupervisionConfig(
        worker_id=WorkerId("sentinel.runtime"),
        worker_name="Sentinel runtime",
        worker_version="1",
        worker_description="Canonical runtime",
        daemon_cycle_interval=1.0,
        health_stale_after=30.0,
        restart_policy=RestartPolicy(),
    )


class SentinelProcess:
    """Temporarily own foreground signals while the scheduler runs synchronously."""

    def __init__(self, scheduler: RuntimeScheduler) -> None:
        self._scheduler = scheduler

    def _request_stop(self, signum: int, frame: object) -> None:
        self._scheduler.request_stop()

    def run(self) -> int:
        try:
            with ExitStack() as handlers:
                for signum in (signal.SIGINT, signal.SIGTERM):
                    previous = signal.getsignal(signum)
                    handlers.callback(signal.signal, signum, previous)
                    signal.signal(signum, self._request_stop)
                try:
                    self._scheduler.run_forever()
                except KeyboardInterrupt:
                    # The daemon handles normal interrupts and shuts down itself.
                    # An escaping interrupt cannot certify completed shutdown.
                    self._scheduler.request_stop()
                    return 1
            return 0
        except Exception:
            logger.exception("Sentinel foreground process failed")
            return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run in the foreground. V1 has no command-line options."""
    try:
        runtime = build_production_runtime()
        config = build_production_config()
        bundle = build_runtime_supervision(runtime, config)
        scheduler = RuntimeScheduler(bundle.daemon)
        return SentinelProcess(scheduler).run()
    except KeyboardInterrupt:
        return 1
    except Exception:
        logger.exception("Sentinel production startup failed")
        return 1
