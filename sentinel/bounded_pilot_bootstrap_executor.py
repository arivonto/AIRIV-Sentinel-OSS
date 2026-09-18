"""Injected-boundary installer for the bounded pilot helper.

This executor has no direct host I/O. It installs only through supplied
boundaries and never restarts Sentinel or executes the pilot remediation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sentinel.bounded_pilot_helper_manifest import (
    BoundedPilotFileManifest,
    BoundedPilotHelperManifest,
)


@dataclass(frozen=True, slots=True)
class BoundedPilotBootstrapAuthorization:
    manifest_fingerprint: str
    helper_install_approved: bool

    def __post_init__(self) -> None:
        if len(self.manifest_fingerprint) != 64:
            raise ValueError("invalid manifest fingerprint")
        if not self.helper_install_approved:
            raise PermissionError("helper install approval required")


@dataclass(frozen=True, slots=True)
class BoundedPilotCommand:
    name: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.name != "daemon_reload":
            raise ValueError("only daemon_reload command is supported")
        if self.argv != (
            "/usr/bin/systemctl",
            "--no-ask-password",
            "daemon-reload",
        ):
            raise ValueError("canonical daemon-reload argv required")


@dataclass(frozen=True, slots=True)
class BoundedPilotCommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True, slots=True)
class BoundedPilotBootstrapResult:
    status: str
    manifest_fingerprint: str
    events: tuple[str, ...]
    error: str | None
    rollback_errors: tuple[str, ...]

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCEEDED"


class BoundedPilotFilesystemBoundary(Protocol):
    def exists(self, path: str) -> bool:
        ...

    def install_exact(self, manifest: BoundedPilotFileManifest) -> None:
        ...

    def verify_exact(self, manifest: BoundedPilotFileManifest) -> bool:
        ...

    def remove_exact(self, manifest: BoundedPilotFileManifest) -> None:
        ...


class BoundedPilotSystemctlBoundary(Protocol):
    def run(
        self,
        command: BoundedPilotCommand,
        timeout: float,
    ) -> BoundedPilotCommandResult:
        ...


class BoundedPilotAuthorizationProbe(Protocol):
    def daemon_status(self) -> str:
        ...

    def shell_status(self) -> str:
        ...


def prepare_bounded_pilot_bootstrap_authorization(
    *,
    manifest: BoundedPilotHelperManifest,
    helper_readiness_ready: bool,
) -> BoundedPilotBootstrapAuthorization:
    if type(manifest) is not BoundedPilotHelperManifest:
        raise TypeError("BoundedPilotHelperManifest required")
    if helper_readiness_ready is not True:
        raise PermissionError("bounded_pilot_helper_gate_not_ready")
    return BoundedPilotBootstrapAuthorization(
        manifest_fingerprint=manifest.fingerprint,
        helper_install_approved=True,
    )


class BoundedPilotBootstrapExecutor:
    def __init__(self, *, timeout: float = 5.0) -> None:
        if type(timeout) not in (int, float) or timeout <= 0:
            raise ValueError("timeout must be positive")
        self._timeout = float(timeout)

    def execute(
        self,
        *,
        manifest: BoundedPilotHelperManifest,
        authorization: BoundedPilotBootstrapAuthorization,
        filesystem: BoundedPilotFilesystemBoundary,
        systemctl: BoundedPilotSystemctlBoundary,
        authorization_probe: BoundedPilotAuthorizationProbe,
    ) -> BoundedPilotBootstrapResult:
        self._validate_authorization(
            manifest=manifest,
            authorization=authorization,
        )

        events: list[str] = []
        artifacts = (manifest.helper, manifest.polkit_rule)

        for artifact in artifacts:
            if filesystem.exists(artifact.destination):
                events.append(f"blocked:collision:{artifact.role}")
                return BoundedPilotBootstrapResult(
                    status="BLOCKED",
                    manifest_fingerprint=manifest.fingerprint,
                    events=tuple(events),
                    error=f"collision:{artifact.role}",
                    rollback_errors=(),
                )

        mutation_started = False

        try:
            for artifact in artifacts:
                filesystem.install_exact(artifact)
                mutation_started = True
                events.append(f"install:{artifact.role}")

                if not filesystem.verify_exact(artifact):
                    raise RuntimeError(f"verify_failed:{artifact.role}")

                events.append(f"verify:{artifact.role}")

            command = BoundedPilotCommand(
                name="daemon_reload",
                argv=(
                    "/usr/bin/systemctl",
                    "--no-ask-password",
                    "daemon-reload",
                ),
            )
            result = systemctl.run(command, self._timeout)
            events.append(f"command:{command.name}:{result.returncode}")
            if not result.succeeded:
                raise RuntimeError("command_failed:daemon_reload")

            daemon_status = authorization_probe.daemon_status()
            events.append(f"probe:daemon:{daemon_status}")
            if daemon_status != "AUTHORIZED":
                raise RuntimeError(
                    "daemon_runtime_authorization_not_granted"
                )

            shell_status = authorization_probe.shell_status()
            events.append(f"probe:shell:{shell_status}")
            if shell_status == "AUTHORIZED":
                raise RuntimeError(
                    "shell_runtime_authorization_must_be_denied"
                )

            return BoundedPilotBootstrapResult(
                status="SUCCEEDED",
                manifest_fingerprint=manifest.fingerprint,
                events=tuple(events),
                error=None,
                rollback_errors=(),
            )

        except Exception as exc:
            if not mutation_started:
                return BoundedPilotBootstrapResult(
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
            return BoundedPilotBootstrapResult(
                status=(
                    "ROLLED_BACK"
                    if not rollback_errors
                    else "ROLLBACK_FAILED"
                ),
                manifest_fingerprint=manifest.fingerprint,
                events=tuple(events),
                error=str(exc),
                rollback_errors=tuple(rollback_errors),
            )

    @staticmethod
    def _validate_authorization(
        *,
        manifest: BoundedPilotHelperManifest,
        authorization: BoundedPilotBootstrapAuthorization,
    ) -> None:
        if type(manifest) is not BoundedPilotHelperManifest:
            raise TypeError("BoundedPilotHelperManifest required")
        if type(authorization) is not BoundedPilotBootstrapAuthorization:
            raise TypeError("BoundedPilotBootstrapAuthorization required")
        if authorization.manifest_fingerprint != manifest.fingerprint:
            raise PermissionError("manifest_fingerprint_mismatch")
        if not authorization.helper_install_approved:
            raise PermissionError("helper install approval required")

    def _rollback(
        self,
        *,
        manifest: BoundedPilotHelperManifest,
        filesystem: BoundedPilotFilesystemBoundary,
        systemctl: BoundedPilotSystemctlBoundary,
        events: list[str],
    ) -> list[str]:
        errors: list[str] = []

        for artifact in (manifest.polkit_rule, manifest.helper):
            if not filesystem.exists(artifact.destination):
                continue
            try:
                if not filesystem.verify_exact(artifact):
                    raise RuntimeError(
                        f"rollback_artifact_mismatch:{artifact.role}"
                    )
                filesystem.remove_exact(artifact)
                events.append(f"rollback:remove:{artifact.role}")
            except Exception as exc:
                errors.append(str(exc))
                events.append(f"rollback:error:{artifact.role}")

        command = BoundedPilotCommand(
            name="daemon_reload",
            argv=(
                "/usr/bin/systemctl",
                "--no-ask-password",
                "daemon-reload",
            ),
        )
        try:
            result = systemctl.run(command, self._timeout)
            events.append(
                f"rollback:command:{command.name}:{result.returncode}"
            )
            if not result.succeeded:
                errors.append("rollback_command_failed:daemon_reload")
        except Exception as exc:
            errors.append(f"rollback_command_exception:daemon_reload:{exc}")
            events.append("rollback:command:daemon_reload:EXCEPTION")

        for artifact in (manifest.polkit_rule, manifest.helper):
            if filesystem.exists(artifact.destination):
                errors.append(
                    f"rollback_artifact_still_present:{artifact.role}"
                )

        events.append(
            "rollback:verification:FAILED"
            if errors
            else "rollback:verification:PASS"
        )
        return errors
