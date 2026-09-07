"""Explicit, startup-free production composition for one supplied runtime."""

from dataclasses import dataclass

from sentinel.runtime import SentinelRuntime

from .daemon import DaemonConfig, OperationalDaemon
from .capability_worker import SentinelCapabilityWorker
from .observability import LiveEvidenceObservability
from .health import HealthMonitor
from .models import WorkerId, WorkerInfo
from .registry import WorkerRegistry
from .runtime_worker import SentinelRuntimeWorker
from .supervisor import RestartPolicy, RuntimeSupervisor


@dataclass(frozen=True)
class RuntimeSupervisionConfig:
    worker_id: WorkerId
    worker_name: str
    worker_version: str
    worker_description: str
    daemon_cycle_interval: float
    health_stale_after: float
    restart_policy: RestartPolicy

    def __post_init__(self) -> None:
        if not isinstance(self.worker_id, WorkerId):
            raise TypeError("worker_id must be WorkerId")
        if not isinstance(self.restart_policy, RestartPolicy):
            raise TypeError("restart_policy must be RestartPolicy")
        for name in ("worker_name", "worker_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.worker_description, str):
            raise TypeError("worker_description must be a string")
        for name in ("daemon_cycle_interval", "health_stale_after"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 0 < value < float("inf")):
                raise ValueError(f"{name} must be a finite positive number")


@dataclass(frozen=True)
class RuntimeSupervisionBundle:
    """Fixed component references; component lifecycles remain mutable."""

    runtime: SentinelRuntime
    runtime_worker: SentinelRuntimeWorker
    worker_info: WorkerInfo
    registry: WorkerRegistry
    health_monitor: HealthMonitor
    supervisor: RuntimeSupervisor
    daemon: OperationalDaemon
    capability_worker: SentinelCapabilityWorker | None = None


def build_runtime_supervision(
    runtime: SentinelRuntime,
    config: RuntimeSupervisionConfig,
) -> RuntimeSupervisionBundle:
    """Wire the canonical supervision chain without starting any component."""
    if not isinstance(runtime, SentinelRuntime):
        raise TypeError("runtime must be SentinelRuntime")
    if not isinstance(config, RuntimeSupervisionConfig):
        raise TypeError("config must be RuntimeSupervisionConfig")

    runtime_worker = SentinelRuntimeWorker(runtime, config.worker_id)
    worker_info = WorkerInfo(
        worker_id=config.worker_id,
        name=config.worker_name,
        version=config.worker_version,
        description=config.worker_description,
    )
    registry = WorkerRegistry()
    registry.register(runtime_worker, worker_info)
    health_monitor = HealthMonitor(registry, stale_after=config.health_stale_after)
    supervisor = RuntimeSupervisor(registry, health_monitor, config.restart_policy)
    daemon = OperationalDaemon(
        supervisor, DaemonConfig(cycle_interval=config.daemon_cycle_interval),
    )
    return RuntimeSupervisionBundle(
        runtime, runtime_worker, worker_info, registry, health_monitor,
        supervisor, daemon,
    )


def build_production_supervision(
    runtime: SentinelRuntime,
    config: RuntimeSupervisionConfig,
) -> RuntimeSupervisionBundle:
    """Add operational driving to the existing lifecycle-only composition.

    Registration order starts the runtime first and stops capability first.
    The existing daemon and scheduler continue to own supervision timing.
    """
    from dataclasses import replace

    bundle = build_runtime_supervision(runtime, config)
    observability = LiveEvidenceObservability()
    runtime.diagnostic.decision_observer = observability.commander_decision
    capability = SentinelCapabilityWorker(
        runtime, interval=config.daemon_cycle_interval,
        observability=observability,
    )
    bundle.registry.register(capability, WorkerInfo(
        capability.worker_id(), "Sentinel capability", "1", "Canonical runtime cycles",
    ))
    return replace(bundle, capability_worker=capability)
