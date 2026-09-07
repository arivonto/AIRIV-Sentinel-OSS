"""Injected-boundary bootstrap executor.

Phase 2.13D.D7C.5.

The executor contains orchestration only. It has no direct host I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.systemd_canary_bootstrap_manifest import (
    BootstrapCommand,
    BootstrapFileManifest,
    BootstrapReadiness,
    CanaryBootstrapManifest,
)


@dataclass(frozen=True, slots=True)
class BootstrapAuthorization:
    manifest_fingerprint: str
    sentinel_hardening_approved: bool
    canary_bootstrap_approved: bool

    def __post_init__(self) -> None:
        if len(self.manifest_fingerprint) != 64:
            raise ValueError("invalid manifest fingerprint")

        if not self.sentinel_hardening_approved:
            raise PermissionError("sentinel approval required")

        if not self.canary_bootstrap_approved:
            raise PermissionError("canary approval required")


@dataclass(frozen=True, slots=True)
class BootstrapCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True, slots=True)
class BootstrapExecutionResult:
    status: str
    manifest_fingerprint: str
    events: tuple[str, ...]
    error: str | None
    rollback_errors: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCEEDED"

    @property
    def recovered_by_rollback(self) -> bool:
        return self.status == "ROLLED_BACK"


class BootstrapFilesystemBoundary(Protocol):
    def exists(self, path: str) -> bool:
        ...

    def install_exact(self, manifest: BootstrapFileManifest) -> None:
        ...

    def verify_exact(self, manifest: BootstrapFileManifest) -> bool:
        ...

    def remove_exact(self, manifest: BootstrapFileManifest) -> None:
        ...


class BootstrapSystemctlBoundary(Protocol):
    def run(
        self,
        command: BootstrapCommand,
        timeout: float,
    ) -> BootstrapCommandResult:
        ...

    def sentinel_active(self) -> bool:
        ...

    def sentinel_no_new_privileges(self) -> bool:
        ...

    def sentinel_invocation_id(self) -> str:
        ...

    def canary_active(self) -> bool:
        ...


class BootstrapAuthorizationProbe(Protocol):
    def daemon_status(self) -> str:
        ...

    def shell_status(self) -> str:
        ...


def prepare_bootstrap_authorization(
    *,
    manifest: CanaryBootstrapManifest,
    readiness: BootstrapReadiness,
) -> BootstrapAuthorization:
    if not isinstance(manifest, CanaryBootstrapManifest):
        raise TypeError("manifest must be CanaryBootstrapManifest")

    if not isinstance(readiness, BootstrapReadiness):
        raise TypeError("readiness must be BootstrapReadiness")

    if not readiness.mutation_ready:
        raise PermissionError("bootstrap_gate_not_ready")

    return BootstrapAuthorization(
        manifest_fingerprint=manifest.fingerprint,
        sentinel_hardening_approved=True,
        canary_bootstrap_approved=True,
    )


class BootstrapExecutor:
    def __init__(self, *, timeout: float = 5.0) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self._timeout = timeout

    def execute(
        self,
        *,
        manifest: CanaryBootstrapManifest,
        authorization: BootstrapAuthorization,
        filesystem: BootstrapFilesystemBoundary,
        systemctl: BootstrapSystemctlBoundary,
        authorization_probe: BootstrapAuthorizationProbe,
    ) -> BootstrapExecutionResult:
        self._validate_authorization(
            manifest=manifest,
            authorization=authorization,
        )

        events: list[str] = []

        artifacts = (
            manifest.sentinel_dropin,
            manifest.canary_unit,
            manifest.polkit_rule,
        )

        for artifact in artifacts:
            if filesystem.exists(artifact.destination):
                events.append(
                    f"blocked:collision:{artifact.role}"
                )

                return BootstrapExecutionResult(
                    status="BLOCKED",
                    manifest_fingerprint=manifest.fingerprint,
                    events=tuple(events),
                    error=f"collision:{artifact.role}",
                    rollback_errors=(),
                )

        before_invocation = systemctl.sentinel_invocation_id()

        if not systemctl.sentinel_active():
            return BootstrapExecutionResult(
                status="BLOCKED",
                manifest_fingerprint=manifest.fingerprint,
                events=("blocked:sentinel_inactive",),
                error="sentinel_inactive",
                rollback_errors=(),
            )

        if systemctl.sentinel_no_new_privileges():
            return BootstrapExecutionResult(
                status="BLOCKED",
                manifest_fingerprint=manifest.fingerprint,
                events=("blocked:unexpected_pre_nnp",),
                error="unexpected_pre_nnp",
                rollback_errors=(),
            )

        if not before_invocation:
            return BootstrapExecutionResult(
                status="BLOCKED",
                manifest_fingerprint=manifest.fingerprint,
                events=("blocked:missing_invocation",),
                error="missing_invocation",
                rollback_errors=(),
            )

        mutation_started = False

        try:
            for artifact in artifacts:
                filesystem.install_exact(artifact)
                mutation_started = True

                events.append(
                    f"install:{artifact.role}"
                )

                if not filesystem.verify_exact(artifact):
                    raise RuntimeError(
                        f"verify_failed:{artifact.role}"
                    )

                events.append(
                    f"verify:{artifact.role}"
                )

            for command in manifest.apply_commands:
                result = systemctl.run(
                    command,
                    self._timeout,
                )

                events.append(
                    f"command:{command.name}:{result.returncode}"
                )

                if not result.succeeded:
                    raise RuntimeError(
                        f"command_failed:{command.name}"
                    )

                if command.name == "restart_sentinel":
                    if not systemctl.sentinel_active():
                        raise RuntimeError(
                            "sentinel_not_active_after_restart"
                        )

                    after_invocation = (
                        systemctl.sentinel_invocation_id()
                    )

                    if not after_invocation:
                        raise RuntimeError(
                            "sentinel_invocation_missing_after_restart"
                        )

                    if after_invocation == before_invocation:
                        raise RuntimeError(
                            "sentinel_invocation_not_changed"
                        )

                    if not systemctl.sentinel_no_new_privileges():
                        raise RuntimeError(
                            "sentinel_nnp_not_enabled"
                        )

                    events.append(
                        "verify:sentinel_restart"
                    )

                if command.name == "start_canary":
                    if not systemctl.canary_active():
                        raise RuntimeError(
                            "canary_not_active"
                        )

                    events.append(
                        "verify:canary_active"
                    )

            daemon_status = authorization_probe.daemon_status()
            events.append(
                f"probe:daemon:{daemon_status}"
            )

            if daemon_status != "AUTHORIZED":
                raise RuntimeError(
                    "daemon_runtime_authorization_not_granted"
                )

            shell_status = authorization_probe.shell_status()
            events.append(
                f"probe:shell:{shell_status}"
            )

            if shell_status == "AUTHORIZED":
                raise RuntimeError(
                    "shell_runtime_authorization_must_be_denied"
                )

            return BootstrapExecutionResult(
                status="SUCCEEDED",
                manifest_fingerprint=manifest.fingerprint,
                events=tuple(events),
                error=None,
                rollback_errors=(),
            )

        except Exception as exc:
            if not mutation_started:
                return BootstrapExecutionResult(
                    status="FAILED_NO_MUTATION",
                    manifest_fingerprint=manifest.fingerprint,
                    events=tuple(events),
                    error=str(exc),
                    rollback_errors=(),
                )

            rollback_errors = self._rollback(
                manifest=manifest,
                filesystem=filesystem,
                systemctl=systemctl,
                events=events,
            )

            status = (
                "ROLLED_BACK"
                if not rollback_errors
                else "ROLLBACK_FAILED"
            )

            return BootstrapExecutionResult(
                status=status,
                manifest_fingerprint=manifest.fingerprint,
                events=tuple(events),
                error=str(exc),
                rollback_errors=tuple(rollback_errors),
            )

    @staticmethod
    def _validate_authorization(
        *,
        manifest: CanaryBootstrapManifest,
        authorization: BootstrapAuthorization,
    ) -> None:
        if not isinstance(manifest, CanaryBootstrapManifest):
            raise TypeError("manifest must be CanaryBootstrapManifest")

        if not isinstance(authorization, BootstrapAuthorization):
            raise TypeError(
                "authorization must be BootstrapAuthorization"
            )

        if authorization.manifest_fingerprint != manifest.fingerprint:
            raise PermissionError(
                "manifest_fingerprint_mismatch"
            )

        if not authorization.sentinel_hardening_approved:
            raise PermissionError(
                "sentinel approval required"
            )

        if not authorization.canary_bootstrap_approved:
            raise PermissionError(
                "canary approval required"
            )

    def _rollback(
        self,
        *,
        manifest: CanaryBootstrapManifest,
        filesystem: BootstrapFilesystemBoundary,
        systemctl: BootstrapSystemctlBoundary,
        events: list[str],
    ) -> list[str]:
        errors: list[str] = []

        command_by_name = {
            command.name: command
            for command in manifest.rollback_commands
        }

        if systemctl.canary_active():
            self._rollback_command(
                name="stop_canary",
                command_by_name=command_by_name,
                systemctl=systemctl,
                events=events,
                errors=errors,
            )

        artifacts_by_path = {
            manifest.sentinel_dropin.destination:
                manifest.sentinel_dropin,
            manifest.canary_unit.destination:
                manifest.canary_unit,
            manifest.polkit_rule.destination:
                manifest.polkit_rule,
        }

        for path in manifest.rollback_remove_paths:
            artifact = artifacts_by_path[path]

            if not filesystem.exists(path):
                continue

            try:
                if not filesystem.verify_exact(artifact):
                    raise RuntimeError(
                        f"rollback_artifact_mismatch:{artifact.role}"
                    )

                filesystem.remove_exact(artifact)

                events.append(
                    f"rollback:remove:{artifact.role}"
                )

            except Exception as exc:
                errors.append(str(exc))
                events.append(
                    f"rollback:error:{artifact.role}"
                )

        self._rollback_command(
            name="daemon_reload_after_remove",
            command_by_name=command_by_name,
            systemctl=systemctl,
            events=events,
            errors=errors,
        )

        self._rollback_command(
            name="restart_sentinel_after_restore",
            command_by_name=command_by_name,
            systemctl=systemctl,
            events=events,
            errors=errors,
        )

        self._rollback_command(
            name="reset_failed_canary",
            command_by_name=command_by_name,
            systemctl=systemctl,
            events=events,
            errors=errors,
        )

        for artifact in (
            manifest.polkit_rule,
            manifest.canary_unit,
            manifest.sentinel_dropin,
        ):
            if filesystem.exists(artifact.destination):
                errors.append(
                    f"rollback_artifact_still_present:{artifact.role}"
                )

        if not systemctl.sentinel_active():
            errors.append(
                "rollback_sentinel_not_active"
            )

        if systemctl.sentinel_no_new_privileges():
            errors.append(
                "rollback_sentinel_nnp_not_restored"
            )

        if systemctl.canary_active():
            errors.append(
                "rollback_canary_still_active"
            )

        if errors:
            events.append(
                "rollback:verification:FAILED"
            )
        else:
            events.append(
                "rollback:verification:PASS"
            )

        return errors

    def _rollback_command(
        self,
        *,
        name: str,
        command_by_name: dict[str, BootstrapCommand],
        systemctl: BootstrapSystemctlBoundary,
        events: list[str],
        errors: list[str],
    ) -> None:
        command = command_by_name[name]

        try:
            result = systemctl.run(
                command,
                self._timeout,
            )

            events.append(
                f"rollback:command:{name}:{result.returncode}"
            )

            if not result.succeeded:
                errors.append(
                    f"rollback_command_failed:{name}"
                )

        except Exception as exc:
            errors.append(
                f"rollback_command_exception:{name}:{exc}"
            )

            events.append(
                f"rollback:command:{name}:EXCEPTION"
            )
