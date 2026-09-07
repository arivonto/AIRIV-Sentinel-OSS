from sentinel.resource_bound_remediation import (
    GenericBoundRemediationEffect,
    ResourceBoundPermitBinding,
)


class _Target:
    @property
    def component_id(self):
        return "systemd:airiv-sentinel-production-remediation-probe.service"

    @property
    def fingerprint(self):
        return "target-fingerprint"

    @property
    def live_eligible(self):
        return True


def _effect():
    return GenericBoundRemediationEffect(
        run_id="run-1",
        incident_id="incident-1",
        component_id=(
            "systemd:airiv-sentinel-production-remediation-probe.service"
        ),
        resource_kind="systemd.service",
        target=_Target(),
        scope_fingerprint="scope-fingerprint",
        action="systemd_restart",
        argv=(
            "sudo",
            "-n",
            "systemctl",
            "restart",
            "airiv-sentinel-production-remediation-probe.service",
        ),
        execution_id="execution-1",
        permit_id="permit-1",
    )


def test_effect_fingerprint_is_exact_canonical_fingerprint_alias():
    effect = _effect()

    assert effect.effect_fingerprint == effect.fingerprint


def test_permit_binding_uses_same_effect_fingerprint_semantics():
    effect = _effect()
    binding = ResourceBoundPermitBinding.from_effect(effect)

    assert binding.effect_fingerprint == effect.fingerprint
    assert binding.effect_fingerprint == effect.effect_fingerprint
