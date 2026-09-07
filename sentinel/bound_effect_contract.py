"""Shared nominal contract for exact bound remediation effects.

The contract deliberately separates remediation-run identity from
resource identity.

TMUX legacy effects historically store run_id on their target.
Generic effects store run_id directly on the effect.

RemediationPolicy must consume policy_run_id from this contract and
must never assume a resource-specific target layout.
"""

from __future__ import annotations


class BoundRemediationEffectContract:
    """Nominal base for exact immutable remediation effects."""

    __slots__ = ()

    @property
    def policy_run_id(self) -> str:
        """Canonical run identifier used by RemediationPolicy."""
        raise NotImplementedError


def validate_bound_effect_contract(
    effect,
) -> None:
    """Require explicit nominal membership and canonical run identity."""

    if not isinstance(
        effect,
        BoundRemediationEffectContract,
    ):
        # Preserve historical error text for locked compatibility.
        raise TypeError(
            "effect must be a BoundRemediationEffect"
        )

    try:
        run_id = effect.policy_run_id
    except (
        AttributeError,
        NotImplementedError,
    ) as exc:
        raise TypeError(
            "bound effect must expose policy_run_id"
        ) from exc

    if (
        not isinstance(run_id, str)
        or not run_id.strip()
    ):
        raise ValueError(
            "bound effect policy_run_id must be non-empty"
        )


def bound_effect_policy_run_id(
    effect,
) -> str:
    """Return the resource-neutral run key used by RemediationPolicy."""

    validate_bound_effect_contract(
        effect
    )

    return effect.policy_run_id.strip()


def bound_effect_target_fingerprint(
    effect,
) -> str:
    """Canonical resource-neutral target fingerprint."""

    validate_bound_effect_contract(
        effect
    )

    value = getattr(
        effect,
        "target_fingerprint",
        None,
    )

    if value is None:
        target = getattr(
            effect,
            "target",
            None,
        )

        value = getattr(
            target,
            "fingerprint",
            None,
        )

    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            "bound effect target fingerprint must be non-empty"
        )

    return value.strip()
