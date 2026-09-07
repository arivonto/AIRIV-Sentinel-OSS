"""D7D.1 corrective bootstrap semantics.

This module defines two narrow architectural corrections discovered by
controlled host validation:

1. polkit .rules installation must create/write the exact final .rules path;
   a hidden temporary file followed only by rename/move into the final name
   is not accepted as sufficient reload evidence.

2. pkcheck --process PID,START_TIME,UID is a synthetic verification surface.
   It may prove rule loading, action details, and resolved user identity, but
   it must not be used as proof of safe-pidfd-derived system_unit,
   no_new_privileges, or the real systemd D-Bus authorization path.

No host mutation or subprocess execution belongs in this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json


CORRECTIVE_SEMANTICS_VERSION = "D7D1-CORRECTIVE-V1"

POLKIT_INSTALL_DIRECT_FINAL_PATH = "DIRECT_FINAL_PATH_CREATE"
POLKIT_INSTALL_HIDDEN_RENAME = "HIDDEN_TEMP_RENAME"

PKCHECK_PROVABLE_CLAIMS = frozenset(
    {
        "rule_loaded",
        "action_id",
        "action_unit_detail",
        "action_verb_detail",
        "subject_user",
    }
)

PKCHECK_FORBIDDEN_PROOF_CLAIMS = frozenset(
    {
        "subject_system_unit",
        "subject_no_new_privileges",
        "real_systemd_dbus_authorization",
    }
)


@dataclass(frozen=True)
class D7D1CorrectiveBootstrapSemantics:
    """Immutable D7D.1 corrective execution semantics."""

    manifest_fingerprint: str
    version: str = CORRECTIVE_SEMANTICS_VERSION
    polkit_install_mode: str = POLKIT_INSTALL_DIRECT_FINAL_PATH
    real_authorization_validation_phase: str = "2.13D.D7D.2"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.manifest_fingerprint, str)
            or not self.manifest_fingerprint.strip()
        ):
            raise ValueError(
                "manifest_fingerprint is required"
            )

        if (
            self.polkit_install_mode
            != POLKIT_INSTALL_DIRECT_FINAL_PATH
        ):
            raise ValueError(
                "D7D.1 requires direct final-path polkit installation"
            )

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return sha256(payload).hexdigest()

    def validate_polkit_install(
        self,
        *,
        destination_path: str,
        write_path: str,
        rename_into_destination: bool,
    ) -> None:
        """Require creation/write at the exact final .rules path."""

        if (
            not destination_path
            or not destination_path.endswith(".rules")
        ):
            raise ValueError(
                "polkit destination must be an exact .rules path"
            )

        if write_path != destination_path:
            raise ValueError(
                "polkit rule must be written directly to final path"
            )

        if rename_into_destination:
            raise ValueError(
                "hidden-temp rename/move cannot establish D7D.1 reload"
            )

    def validate_pkcheck_claim(
        self,
        claim: str,
    ) -> None:
        """Fail closed when pkcheck is used beyond its evidence scope."""

        if claim in PKCHECK_FORBIDDEN_PROOF_CLAIMS:
            raise ValueError(
                f"pkcheck cannot prove {claim}; "
                "real safe-pidfd/systemd D-Bus validation is deferred "
                f"to {self.real_authorization_validation_phase}"
            )

        if claim not in PKCHECK_PROVABLE_CLAIMS:
            raise ValueError(
                f"unknown D7D.1 pkcheck claim: {claim}"
            )


def canonical_d7d1_corrective_semantics(
    manifest_fingerprint: str,
) -> D7D1CorrectiveBootstrapSemantics:
    """Return canonical corrective semantics bound to one manifest."""

    return D7D1CorrectiveBootstrapSemantics(
        manifest_fingerprint=manifest_fingerprint,
    )
