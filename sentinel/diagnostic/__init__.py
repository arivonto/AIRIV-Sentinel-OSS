"""AIRIV Sentinel Diagnostic Engine."""

from .engine import (
    DiagnosticActionSelector,
    DiagnosticEngine,
    DiagnosticStepResult,
)

__all__ = [
    "DiagnosticActionSelector",
    "DiagnosticEngine",
    "DiagnosticStepResult",
    "RuntimeDiagnosticConfig",
    "RuntimeDiagnosticCoordinator",
]

from .commander_handoff import (
    CommanderHandoff,
    RemediationActionRequest,
)

# Runtime coordinator exports are intentionally lazy.
#
# Lower-level modules such as sentinel.diagnostic.commander_handoff are used
# by systemd evidence/authorization boundaries. Importing the diagnostic
# package must therefore not eagerly initialize RuntimeDiagnosticCoordinator,
# which depends on remediation_policy.
_RUNTIME_COORDINATOR_EXPORTS = frozenset(('RuntimeDiagnosticConfig', 'RuntimeDiagnosticCoordinator'))


def __getattr__(name):
    if name in _RUNTIME_COORDINATOR_EXPORTS:
        from importlib import import_module

        module = import_module(
            f"{__name__}.runtime_coordinator"
        )
        value = getattr(module, name)

        # Preserve ordinary package-export behavior after first access.
        globals()[name] = value
        return value

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )


def __dir__():
    return sorted(
        set(globals())
        | set(_RUNTIME_COORDINATOR_EXPORTS)
    )

