"""Repository deployment contract; never apply installation or activate services."""

import os
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'deployment/systemd/airiv-sentinel.service.in'
RENDER = ROOT / 'scripts/render_systemd_service.sh'
INSTALL = ROOT / 'scripts/install_systemd_service.sh'


def run(script, *args, **kwargs):
    return subprocess.run([str(script), *map(str, args)], text=True,
                          capture_output=True, **kwargs)


def arguments(output):
    return ['--user', 'testuser', '--group', 'testgroup', '--repo', ROOT,
            '--python', ROOT / 'venv/bin/python', '--output', output]


@pytest.mark.parametrize('path', [TEMPLATE, RENDER, INSTALL])
def test_artifact_exists(path):
    assert path.is_file()


@pytest.mark.parametrize('line', [
    '[Unit]', '[Service]', '[Install]', 'Description=AIRIV Sentinel',
    'After=network-online.target', 'Wants=network-online.target', 'Type=simple',
    'Restart=on-failure', 'KillSignal=SIGTERM', 'StandardOutput=journal',
    'StandardError=journal', 'Environment=PYTHONUNBUFFERED=1',
    'WantedBy=multi-user.target', 'UMask=0027', 'User=@SERVICE_USER@',
    'Group=@SERVICE_GROUP@', 'WorkingDirectory=@REPO_ROOT@',
    'ExecStart=@PYTHON_EXECUTABLE@ -m sentinel',
])
def test_template_contract(line):
    assert line in TEMPLATE.read_text().splitlines()


@pytest.mark.parametrize('name', ['RestartSec', 'TimeoutStopSec'])
def test_finite_intervals(name):
    value = re.search(rf'^{name}=(\d+)$', TEMPLATE.read_text(), re.M)
    assert value and 0 < int(value[1]) <= 30


@pytest.mark.parametrize('script', [RENDER, INSTALL])
def test_help_and_shell(script):
    assert os.access(script, os.X_OK)
    assert 'set -euo pipefail' in script.read_text()
    assert run(script, '--help').returncode == 0
    assert subprocess.run(['bash', '-n', str(script)]).returncode == 0


def test_no_forbidden_template_content():
    text = TEMPLATE.read_text()
    for forbidden in ['/home/arivonto', 'User=root', 'nohup', 'tmux', 'screen',
                      '&', 'while true', 'fork', 'setsid', 'ProtectSystem=',
                      'ProtectHome=', 'PrivateDevices=', 'NoNewPrivileges=',
                      'CapabilityBoundingSet=', 'RestrictAddressFamilies=']:
        assert forbidden not in text


@pytest.mark.parametrize('option,value', [
    ('--python', '/nonexistent/python'), ('--python', ''),
    ('--repo', '/nonexistent/repo'), ('--user', ''), ('--group', ''),
    ('--output', ''), ('--user', 'root'), ('--user', 'bad\nUser=root'),
    ('--group', '%u'),
])
def test_reject_invalid_arguments(tmp_path, option, value):
    assert run(RENDER, *arguments(tmp_path / 'unit'), option, value).returncode != 0


def test_reject_non_executable_and_file_repo(tmp_path):
    plain = tmp_path / 'plain'
    plain.write_text('data')
    for option in ['--python', '--repo']:
        assert run(RENDER, *arguments(tmp_path / 'unit'), option, plain).returncode != 0


def mutation_snapshot(path):
    def metadata(value):
        # Reading content can update atime; retain all mutation-relevant fields.
        return {name: getattr(value, name) for name in (
            'st_mode', 'st_ino', 'st_dev', 'st_nlink', 'st_uid', 'st_gid',
            'st_size', 'st_mtime_ns', 'st_ctime_ns',
        )}

    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return (
        metadata(info),
        os.readlink(path) if path.is_symlink() else None,
        metadata(path.stat()) if path.is_symlink() and path.exists() else None,
        path.read_bytes() if path.is_file() else None,
    )


def test_mutation_snapshot_ignores_read_access_time(tmp_path):
    target = tmp_path / 'unit'
    target.write_bytes(b'[Unit]\nDescription=Snapshot test\n')
    os.utime(target, ns=(1_000_000_000, 2_000_000_000))
    before = mutation_snapshot(target)
    assert mutation_snapshot(target) == before
    target.write_bytes(b'[Unit]\nDescription=Changed unit!\n')
    assert mutation_snapshot(target) != before


@pytest.fixture
def installer_env(tmp_path):
    """Simulate identities and capture apply operations entirely under tmp_path."""
    scripts = {
        'id': '''case "$*" in
    -u) printf '%s\\n' "$TEST_UID" ;;
    -un) echo operator ;;
    '-u arivonto'|'-u operator'|'-u testuser') echo 1000 ;;
    '-u root'|'-u root_alias') echo 0 ;;
    '-gn arivonto') echo operators ;;
    '-gn operator'|-gn) echo operator_group ;;
    '-gn testuser') echo testgroup ;;
    *) exit 1 ;;
esac
''',
        'install': '''printf 'install\\n' >> "$TEST_COMMANDS"
[[ "$#" == 9 && "$1" == -o && "$2" == root && "$3" == -g &&
   "$4" == root && "$5" == -m && "$6" == 0644 && "$7" == -- &&
   "$9" == /etc/systemd/system/airiv-sentinel.service ]] || exit 98
cp -- "$8" "$TEST_UNIT"
''',
        'systemctl': 'printf "systemctl %s\\n" "$*" >> "$TEST_COMMANDS"\n',
        'sudo': 'printf "sudo\\n" >> "$TEST_COMMANDS"; exit 99\n',
    }
    for name, body in scripts.items():
        stub = tmp_path / name
        stub.write_text('#!/bin/bash\nset -eu\n' + body)
        stub.chmod(0o755)
    return dict(os.environ, PATH=f'{tmp_path}:{os.environ["PATH"]}',
                TEST_UID='1000', SUDO_USER='',
                TEST_COMMANDS=str(tmp_path / 'commands'),
                TEST_UNIT=str(tmp_path / 'captured.service'))


def test_apply_requires_root(installer_env):
    result = run(INSTALL, '--apply', env=installer_env)
    assert result.returncode != 0
    assert 'Apply requires existing root privileges' in result.stderr
    assert not Path(installer_env['TEST_COMMANDS']).exists()


@pytest.mark.parametrize('sudo_user,options', [
    ('', []), ('root', []), ('unknown', []),
    ('arivonto', ['--user', 'root']),
    ('arivonto', ['--user', 'root_alias']),
    ('arivonto', ['--user', '']),
    ('arivonto', ['--user', 'unknown']),
])
def test_root_invalid_service_user_fails_closed(installer_env, sudo_user, options):
    installer_env.update(TEST_UID='0', SUDO_USER=sudo_user)
    result = run(INSTALL, '--apply', *options, env=installer_env)
    assert result.returncode != 0
    assert 'Error:' in result.stderr
    assert not Path(installer_env['TEST_COMMANDS']).exists()


def test_apply_is_explicit_and_only_reloads():
    text = INSTALL.read_text()
    assert 'apply=false' in text and '--apply)' in text
    assert 'if "$apply"; then' in text
    commands = re.findall(r'^\s*systemctl\s+(.+)$', text, re.M)
    assert commands == ['daemon-reload']
    assert not re.search(r'\bsystemctl\s+(start|stop|restart|enable|disable)\b', text)
    assert not re.search(r'^\s*sudo\b', text, re.M)
    assert 'systemctl' not in RENDER.read_text()
    assert 'eval ' not in RENDER.read_text()


def test_deployment_has_no_business_semantics():
    text = '\n'.join(p.read_text() for p in [TEMPLATE, RENDER, INSTALL])
    for name in ['Incident', 'Diagnosis', 'Commander', 'RemediationPolicy',
                 'Verification', 'sentinel.runtime']:
        assert name not in text


def test_production_module_entrypoint():
    text = (ROOT / 'sentinel/__main__.py').read_text()
    assert 'from sentinel.worker.entrypoint import main' in text
    assert 'raise SystemExit(main())' in text
