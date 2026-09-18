"""Architecture locks for the Gate 4 least-privilege Actions host bridge."""

from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "airiv_gate4_host_validator.py"
BOOTSTRAP = ROOT / "scripts" / "bootstrap_airiv_host_bridge.sh"
UNIT = ROOT / "deploy" / "systemd" / "airiv-sentinel-gate4-live-retest.service"
WORKFLOW = ROOT / ".github" / "workflows" / "gate4-host-live-retest.yml"


def test_root_validator_is_standalone_and_exact_target():
    source = VALIDATOR.read_text()
    tree = ast.parse(source)

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not any(name == "sentinel" or name.startswith("sentinel.") for name in imported)
    assert 'PROBE = "airiv-sentinel-production-remediation-probe.service"' in source
    assert 'item.get("action") == "RESTART"' in source
    assert 'systemctl("stop", PROBE)' in source
    assert 'systemctl("restart", PROBE)' not in source
    assert 'systemctl("start", PROBE)' not in source
    assert "prior_gate4_durable_effect_attempt_exists" in source
    assert "production_retry_budget_exhausted" in source
    assert "unexpected_second_probe_restart" in source
    assert "gate4_delayed_verification_closeout" in source
    assert "unexpected_second_gate4_attempt" in source
    assert 'continuation_closeout=True' in source
    assert 'delayed_verification=True' in source
    assert 'prior_outcome_verification_succeeded=False' in source
    assert 'prior_outcome_final_outcome="UNRESOLVED"' in source
    assert 'REVIEWED_HOST_SHA = "d1e32bdf3ee4881108cf7fa74f7d3aea4a0e7c57"' in source
    assert '"tests/test_gate4_host_bridge_architecture_v1.py"' in source
    assert '"deploy/systemd/airiv-sentinel-gate4-live-retest.service"' in source


def test_root_validator_service_is_hardened_and_not_boot_enabled_by_unit():
    source = UNIT.read_text()

    assert "Type=oneshot" in source
    assert "User=root" in source
    assert "ExecStart=/usr/bin/python3 /usr/local/libexec/airiv-sentinel-gate4-live-retest" in source
    assert "NoNewPrivileges=yes" in source
    assert "ProtectSystem=strict" in source
    assert "ProtectHome=read-only" in source
    assert "ReadWritePaths=/var/lib/airiv-sentinel-host-bridge" in source
    assert "Environment=GIT_CONFIG_COUNT=1" in source
    assert "Environment=GIT_CONFIG_KEY_0=safe.directory" in source
    assert "Environment=GIT_CONFIG_VALUE_0=/home/arivonto/airiv/airiv-sentinel" in source
    assert "safe.directory=*" not in source


def test_actions_workflow_is_not_a_general_host_shell_bridge():
    source = WORKFLOW.read_text()

    assert "workflow_dispatch:" in source
    assert "host/gate4-live-command" in source
    assert "host_commands/gate4-live-retest.trigger" in source
    assert "github.ref == 'refs/heads/main'" in source
    assert "github.ref == 'refs/heads/host/gate4-live-command'" in source
    assert "runs-on: [self-hosted, linux, x64, airiv-sentinel-host]" in source
    assert "actions/checkout" not in source
    assert "sudo " not in source
    assert "/usr/bin/systemctl start airiv-sentinel-gate4-live-retest.service" in source
    assert "/usr/bin/systemctl stop" not in source
    assert "/usr/bin/systemctl restart" not in source
    assert 'data.get("continuation_closeout") is True' in source
    assert 'data.get("delayed_verification") is True' in source
    assert 'data.get("fault_injected") is False' in source


def test_bootstrap_pins_runner_and_sandboxes_arbitrary_workflow_code():
    source = BOOTSTRAP.read_text()

    assert 'RUNNER_VERSION="2.337.0"' in source
    assert 'RUNNER_SHA256="70920811a4f8ad4328818682bca5c6469c1c942fab52448868071d0063816613"' in source
    assert "RUNNER_SHA256=VERIFIED" in source
    assert "NoNewPrivileges=yes" in source
    assert "ProtectHome=yes" in source
    assert "ProtectSystem=strict" in source
    assert 'subject.user == "${RUNNER_USER}"' in source
    assert 'action.lookup("unit") == "airiv-sentinel-gate4-live-retest.service"' in source
    assert 'action.lookup("verb") == "start"' in source
    assert "GENERAL_SUDO=NONE" in source
