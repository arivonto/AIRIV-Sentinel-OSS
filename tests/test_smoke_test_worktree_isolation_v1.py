"""Regression contract for AIRIV Sentinel smoke-test worktree isolation."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE_TEST = ROOT / "scripts" / "smoke_test.py"


def _source() -> str:
    return SMOKE_TEST.read_text(encoding="utf-8")


def test_smoke_test_does_not_pin_canonical_checkout():
    source = _source()

    assert 'os.path.expanduser("~/airiv/airiv-sentinel")' not in source
    assert "~/airiv/airiv-sentinel/config/identities.yaml" not in source


def test_smoke_test_derives_repository_root_from_own_location():
    source = _source()

    assert "REPO_ROOT" in source
    assert "os.path.abspath(__file__)" in source
    assert "sys.path.insert(" in source


def test_smoke_test_configuration_uses_same_repository_root():
    source = _source()

    assert "config_path = os.path.join(" in source
    assert "REPO_ROOT" in source
    assert '"config"' in source
    assert '"identities.yaml"' in source
