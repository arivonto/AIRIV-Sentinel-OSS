"""Architecture locks for the narrow self-hosted main deployment bridge."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPLOYER = ROOT / "scripts" / "airiv_host_deploy_main.sh"
REPO_SYNC = ROOT / "scripts" / "airiv_host_repo_sync.sh"
BOOTSTRAP = ROOT / "scripts" / "bootstrap_airiv_host_deploy_bridge.sh"
DEPLOY_UNIT = ROOT / "deploy" / "systemd" / "airiv-sentinel-host-deploy-main.service"
REPO_SYNC_UNIT = ROOT / "deploy" / "systemd" / "airiv-sentinel-host-repo-sync.service"
WORKFLOW = ROOT / ".github" / "workflows" / "host-deploy-main.yml"


def test_repo_sync_helper_is_fixed_owner_fast_forward_only():
    source = REPO_SYNC.read_text()
    assert 'REPO="/home/arivonto/airiv/airiv-sentinel"' in source
    assert '[[ "$(id -u)" == "1000" ]]' in source
    assert '[[ "$(id -g)" == "1000" ]]' in source
    assert 'git -C "${REPO}" fetch --no-tags origin main' in source
    assert 'merge-base --is-ancestor' in source
    assert 'git -C "${REPO}" merge --ff-only origin/main' in source
    assert 'venv/bin/python" -m compileall' in source
    assert 'git reset' not in source
    assert 'git rebase' not in source
    assert 'git push' not in source
    assert 'sudo ' not in source


def test_root_deployer_never_switches_identity_or_mutates_git():
    source = DEPLOYER.read_text()
    assert 'REPO_SYNC_UNIT="airiv-sentinel-host-repo-sync.service"' in source
    assert '/usr/bin/systemctl start "${REPO_SYNC_UNIT}"' in source
    assert 'setpriv' not in source
    assert 'runuser ' not in source
    assert 'sudo ' not in source
    assert 'su ' not in source
    assert 'git_owner' not in source
    assert ' merge --ff-only ' not in source
    assert ' fetch --no-tags ' not in source
    assert 'root_git()' in source
    assert 'GIT_CONFIG_KEY_0=safe.directory' in source


def test_root_deployer_validates_helper_result_and_reviewed_sources():
    source = DEPLOYER.read_text()
    assert 'REPO_SYNC_RESULT="/var/lib/airiv-sentinel-host-repo-sync/result.env"' in source
    assert 'repo_sync_result_unknown_key' in source
    assert 'repo_sync_result_schema_invalid' in source
    assert 'repo_head_mismatch_after_sync' in source
    assert 'origin_main_mismatch_after_sync' in source
    assert 'repository_dirty_after_sync' in source
    assert 'verify_source_matches_head' in source
    assert 'root_git hash-object "${path}"' in source
    assert 'root_git rev-parse "HEAD:${rel}"' in source
    assert 'trusted_component_worktree_mismatch' in source


def test_root_self_update_uses_dedicated_atomic_bridge_directory():
    source = DEPLOYER.read_text()
    assert 'BRIDGE_BIN="${RESULT_ROOT}/bin"' in source
    assert 'DEPLOYER_TARGET="${BRIDGE_BIN}/airiv-sentinel-host-deploy-main"' in source
    assert 'atomic_install_exec()' in source
    assert 'mktemp "${dir}/.airiv-install.XXXXXX"' in source
    assert 'mv -f "${tmp}" "${target}"' in source
    assert 'sync -f "${dir}"' in source
    assert 'atomic_install_exec "${DEPLOYER_SOURCE}" "${DEPLOYER_TARGET}" "deployer_self_update_failed"' in source
    assert '/usr/local/libexec/airiv-sentinel-host-deploy-main' not in source
    assert '/etc/polkit' not in source
    assert '/etc/sudoers' not in source
    assert 'chmod 777' not in source
    assert 'chown -R' not in source


def test_other_root_updates_use_exact_existing_allowlisted_targets():
    source = DEPLOYER.read_text()
    expected = (
        '/usr/local/libexec/airiv-sentinel-host-repo-sync',
        '/usr/local/libexec/airiv-sentinel-gate4-live-retest',
        '/etc/systemd/system/airiv-sentinel-host-deploy-main.service',
        '/etc/systemd/system/airiv-sentinel-host-repo-sync.service',
        '/etc/systemd/system/airiv-sentinel-gate4-live-retest.service',
    )
    for path in expected:
        assert path in source
    assert 'sync_exact_existing_file()' in source
    assert '[[ -f "${target}" ]] || fail "${reason}_target_missing"' in source
    assert '[[ ! -L "${target}" ]] || fail "${reason}_target_symlink_denied"' in source
    assert '/usr/bin/cmp -s "${source}" "${target}"' in source
    assert '/usr/bin/cp --reflink=never --no-preserve=mode,ownership,timestamps --' in source
    assert 'sync_exact_existing_file "${REPO_SYNC_SOURCE}" "${REPO_SYNC_TARGET}" 0755 "repo_sync_update_failed"' in source
    assert 'sync_exact_existing_file "${GATE4_VALIDATOR_SOURCE}" "${GATE4_VALIDATOR_TARGET}" 0755 "gate4_validator_update_failed"' in source
    assert 'sync_exact_existing_file "${DEPLOY_UNIT_SOURCE}" "${DEPLOY_UNIT_TARGET}" 0644 "deploy_unit_update_failed"' in source
    assert 'sync_exact_existing_file "${REPO_SYNC_UNIT_SOURCE}" "${REPO_SYNC_UNIT_TARGET}" 0644 "repo_sync_unit_update_failed"' in source
    assert 'sync_exact_existing_file "${GATE4_UNIT_SOURCE}" "${GATE4_UNIT_TARGET}" 0644 "gate4_unit_update_failed"' in source
    assert '/usr/bin/install -o root -g root -m 0755 "${REPO_SYNC_SOURCE}" "${REPO_SYNC_TARGET}"' not in source
    assert '/usr/bin/install -o root -g root -m 0755 "${GATE4_VALIDATOR_SOURCE}" "${GATE4_VALIDATOR_TARGET}"' not in source
    assert '/usr/bin/install -o root -g root -m 0644 "${DEPLOY_UNIT_SOURCE}" "${DEPLOY_UNIT_TARGET}"' not in source
    assert '/usr/bin/systemctl daemon-reload' in source
    assert 'trusted_component_symlink_denied' in source


def test_root_deployer_tracks_runtime_activation_before_noop():
    source = DEPLOYER.read_text()
    assert 'DEPLOYED_HEAD_FILE="${RESULT_ROOT}/deployed-main-head"' in source
    assert 'read_deployed_head()' in source
    assert 'record_deployed_head()' in source
    assert '[[ "${OLD_HEAD}" == "${NEW_HEAD}" && "${DEPLOYED_HEAD}" == "${NEW_HEAD}" ]]' in source
    assert 'record "PASS" "already_current"' in source
    assert 'DEPLOYMENT=NOOP_MAIN_CURRENT_RUNTIME_CURRENT_BRIDGE_SYNCED' in source
    assert 'record "PASS" "current_head_activated_and_restarted"' in source
    assert 'record "PASS" "fast_forward_deployed_and_restarted"' in source
    restart_pos = source.index('systemctl restart "${SENTINEL}"')
    marker_pos = source.index('record_deployed_head\n')
    assert restart_pos < marker_pos


def test_root_deployer_restarts_only_sentinel_and_only_after_sync():
    source = DEPLOYER.read_text()
    helper_pos = source.index('/usr/bin/systemctl start "${REPO_SYNC_UNIT}"')
    sync_pos = source.index('sync_trusted_bridge_components\n')
    restart_pos = source.index('systemctl restart "${SENTINEL}"')
    assert helper_pos < sync_pos < restart_pos
    assert source.count('systemctl restart "${SENTINEL}"') == 1


def test_repo_sync_unit_runs_as_owner_and_is_not_boot_enabled():
    source = REPO_SYNC_UNIT.read_text()
    assert "Type=oneshot" in source
    assert "User=arivonto" in source
    assert "Group=arivonto" in source
    assert "ExecStart=/usr/local/libexec/airiv-sentinel-host-repo-sync" in source
    assert "StateDirectory=airiv-sentinel-host-repo-sync" in source
    assert "NoNewPrivileges=yes" in source
    assert "ProtectSystem=strict" in source
    assert "ProtectHome=read-only" in source
    rw_line = next(line for line in source.splitlines() if line.startswith("ReadWritePaths="))
    assert "/home/arivonto/airiv/airiv-sentinel" in rw_line
    assert "/var/lib/airiv-sentinel-host-repo-sync" in rw_line
    assert "WantedBy=" not in source


def test_root_deploy_unit_uses_dedicated_executor_and_no_repo_write_access():
    source = DEPLOY_UNIT.read_text()
    assert "User=root" in source
    assert "ExecStart=/var/lib/airiv-sentinel-host-bridge/bin/airiv-sentinel-host-deploy-main" in source
    assert "NoNewPrivileges=yes" in source
    assert "ProtectSystem=strict" in source
    assert "ProtectHome=read-only" in source
    rw_line = next(line for line in source.splitlines() if line.startswith("ReadWritePaths="))
    assert "/home/arivonto/airiv/airiv-sentinel" not in rw_line
    assert "/var/lib/airiv-sentinel-host-bridge" in rw_line
    assert "/usr/local/libexec/airiv-sentinel-host-deploy-main" not in rw_line
    assert "/usr/local/libexec/airiv-sentinel-host-repo-sync" in rw_line
    assert "/etc/systemd/system/airiv-sentinel-host-repo-sync.service" in rw_line
    assert "/usr/local/libexec " not in rw_line
    assert "/etc/systemd/system " not in rw_line
    assert "WantedBy=" not in source


def test_workflow_has_no_checkout_sudo_or_direct_service_restart():
    source = WORKFLOW.read_text()
    assert "host/deploy-main-command" in source
    assert "host_commands/deploy-main.trigger" in source
    assert "runs-on: [self-hosted, linux, x64, airiv-sentinel-host]" in source
    assert "actions/checkout" not in source
    assert "sudo " not in source
    assert "/usr/bin/systemctl start airiv-sentinel-host-deploy-main.service" in source
    assert "/usr/bin/systemctl restart airiv-sentinel.service" not in source
    assert "current_head_activated_and_restarted" in source


def test_bootstrap_installs_dedicated_deployer_and_helper_without_polkit_broadening():
    source = BOOTSTRAP.read_text()
    assert 'BRIDGE_BIN="/var/lib/airiv-sentinel-host-bridge/bin"' in source
    assert 'DEPLOY_TARGET="${BRIDGE_BIN}/airiv-sentinel-host-deploy-main"' in source
    assert 'REPO_SYNC_TARGET="/usr/local/libexec/airiv-sentinel-host-repo-sync"' in source
    assert 'REPO_SYNC_UNIT_TARGET="/etc/systemd/system/airiv-sentinel-host-repo-sync.service"' in source
    assert 'subject.user == "${RUNNER_USER}"' in source
    assert 'action.lookup("verb") == "start"' in source
    assert 'action.lookup("unit") == "airiv-sentinel-gate4-live-retest.service"' in source
    assert 'action.lookup("unit") == "airiv-sentinel-host-deploy-main.service"' in source
    assert 'action.lookup("unit") == "airiv-sentinel-host-repo-sync.service"' not in source
    assert "GENERAL_SUDO=NONE" in source
    assert "safe.directory=*" not in source
