import ast
import inspect
import subprocess
import sys

import pytest

from sentinel import remediation_policy, systemd_production_commander_authorization
from sentinel import systemd_production_approval_issuance, systemd_production_activation_consumption
from sentinel.runtime import SentinelRuntime


@pytest.mark.parametrize('modules', [
    ('sentinel.remediation_policy',),
    ('sentinel.systemd_production_commander_authorization',),
    ('sentinel.remediation_policy', 'sentinel.systemd_production_commander_authorization'),
    ('sentinel.systemd_production_commander_authorization', 'sentinel.remediation_policy'),
])
def test_independent_imports_and_both_orders(modules):
    result = subprocess.run(
        [sys.executable, '-c', '\n'.join(f'import {module}' for module in modules)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_authorization_facts_do_not_import_or_define_policy_authority():
    tree = ast.parse(inspect.getsource(systemd_production_commander_authorization))
    forbidden = {'RemediationPolicy', 'PolicyDecision', 'RemediationPolicyResult',
                 'RemediationDecision', 'BoundRemediationAuthorization', 'ALLOW', 'DENY'}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            assert all(alias.name.split('.')[-1] not in forbidden for alias in node.names)
            assert all('remediation_policy' not in alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                assert 'remediation_policy' not in (node.module or '')
        if isinstance(node, (ast.Name, ast.Attribute)):
            assert (node.id if isinstance(node, ast.Name) else node.attr) not in forbidden
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            assert node.value not in {'ALLOW', 'DENY'}
    policy_tree = ast.parse(inspect.getsource(remediation_policy))
    assert any(isinstance(node, ast.ImportFrom)
               and node.module == 'sentinel.systemd_production_commander_authorization'
               and any(alias.name == 'SystemdProductionCommanderAuthorizationContext'
                       for alias in node.names) for node in ast.walk(policy_tree))


def calls(module):
    return {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
            for node in ast.walk(ast.parse(inspect.getsource(module)))
            if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))}


def test_authority_and_no_effect_calls():
    forbidden = {'execute', 'execute_verified', 'execute_argv', 'resolve', 'verify',
                 'invoke_explicit', 'run', 'Popen', 'system', 'systemctl'}
    for module in (remediation_policy, systemd_production_commander_authorization,
                   systemd_production_approval_issuance, systemd_production_activation_consumption):
        assert not calls(module) & forbidden
    for module in (systemd_production_commander_authorization,
                   systemd_production_approval_issuance, systemd_production_activation_consumption):
        assert not calls(module) & {'evaluate', 'evaluate_bound', 'evaluate_systemd_production_bound',
                                    'RemediationDecision', 'BoundRemediationAuthorization'}
    for module in (remediation_policy, systemd_production_commander_authorization):
        assert not calls(module) & {'issue', 'consume'}
    assert not calls(remediation_policy) & {'records', 'open', 'append'}


def test_no_runtime_enablement_or_context_wiring():
    runtime = SentinelRuntime()
    for name in ('systemd_production_activation_runtime_bridge',
                 'systemd_production_runtime_delegation_bridge',
                 'systemd_production_runtime_invocation',
                 'systemd_production_execution_dispatch_gate'):
        assert getattr(runtime, name).enabled is False
    assert runtime.policy.list_systemd_production_targets() == ()
    tree = ast.parse(inspect.getsource(SentinelRuntime))
    assert sum(isinstance(node, ast.keyword) and node.arg == 'enabled'
               and isinstance(node.value, ast.Constant) and node.value.value is False
               for node in ast.walk(tree)) >= 4
    assert 'commander_authorization' not in inspect.getsource(SentinelRuntime)
