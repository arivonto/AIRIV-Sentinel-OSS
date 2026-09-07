import ast
import inspect

from sentinel import systemd_production_approval_issuance as module
from sentinel.runtime import SentinelRuntime
from sentinel.systemd_production_target_policy import SystemdProductionTargetRule


def test_issuer_call_surface():
    tree = ast.parse(inspect.getsource(module))
    calls = [node.func.id if isinstance(node.func, ast.Name) else node.func.attr
             for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, (ast.Name, ast.Attribute))]
    assert calls.count('SystemdProductionActivationGrant') == 1
    assert not set(calls) & {'consume', 'execute', 'execute_verified', 'execute_argv',
        'evaluate', 'evaluate_bound', 'evaluate_systemd_production_bound', 'resolve',
        'verify', 'invoke_explicit', 'run', 'Popen', 'system'}
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert set(imports) <= {'dataclasses', 'pathlib', 'sentinel.resource_bound_remediation',
        'sentinel.systemd_dispatch_evidence_binding', 'sentinel.systemd_evidence_plan_handoff',
        'sentinel.systemd_production_activation', 'sentinel.systemd_production_preparation',
        'sentinel.systemd_production_runtime_guard'}


def test_runtime_inert_and_allowlist_empty():
    runtime = SentinelRuntime()
    for name in ('systemd_production_activation_runtime_bridge',
                 'systemd_production_runtime_delegation_bridge',
                 'systemd_production_runtime_invocation',
                 'systemd_production_execution_dispatch_gate'):
        assert getattr(runtime, name).enabled is False
    assert runtime.policy.list_systemd_production_targets() == ()
    assert 'approval_issuance' not in inspect.getsource(SentinelRuntime)
    assert 'COMMANDER_ONLY' in inspect.getsource(SystemdProductionTargetRule)
