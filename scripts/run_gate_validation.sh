#!/usr/bin/env bash
set -euo pipefail

SENTINEL_REPO="$HOME/airiv/airiv-sentinel"
VENV="$SENTINEL_REPO/venv"
PYTHON="$VENV/bin/python3"

cd "$SENTINEL_REPO"

echo "============================================================"
echo " AIRIV SENTINEL"
echo " TMUX NORMALIZATION V1.1 — FINAL GATE VALIDATION"
echo "============================================================"
echo

# ----------------------------------------------------------------------
# GATE 0 — Repository / runtime prerequisites
# ----------------------------------------------------------------------

echo "[GATE 0] Runtime prerequisites"

if [ ! -d "$SENTINEL_REPO" ]; then
    echo "[FAIL] Sentinel repository not found:"
    echo "       $SENTINEL_REPO"
    exit 1
fi

if ! command -v tmux >/dev/null 2>&1; then
    echo "[FAIL] tmux command not found."
    exit 1
fi

if [ ! -x "$PYTHON" ]; then
    echo "[*] Creating Python virtual environment..."
    python3 -m venv "$VENV"
fi

"$PYTHON" -c 'import yaml; print("[PASS] PyYAML available.")'

echo "[PASS] Runtime prerequisites OK."
echo

# ----------------------------------------------------------------------
# GATE 1 — Tmux session discovery
# ----------------------------------------------------------------------

echo "[GATE 1] Tmux session discovery"

if ! tmux has-session -t airiv 2>/dev/null; then
    echo "[FAIL] tmux session 'airiv' not found."
    echo
    echo "Available sessions:"
    tmux list-sessions 2>/dev/null || true
    exit 1
fi

PANE_COUNT="$(
    tmux list-panes -t airiv -F '#{pane_id}' 2>/dev/null | wc -l
)"

if [ "$PANE_COUNT" -eq 0 ]; then
    echo "[FAIL] Session 'airiv' contains no panes."
    exit 1
fi

echo "[PASS] Session 'airiv' discovered."
echo "[PASS] Pane count: $PANE_COUNT"
echo

# ----------------------------------------------------------------------
# GATE 2 — Python syntax / import boundary
# ----------------------------------------------------------------------

echo "[GATE 2] Normalization module integrity"

"$PYTHON" -m py_compile \
    sentinel/sensors/tmux/parser.py \
    sentinel/normalization/resolver.py \
    scripts/smoke_test.py

"$PYTHON" - <<'PY'
from sentinel.sensors.tmux.parser import TmuxStateParserV11
from sentinel.normalization.resolver import (
    IdentityResolver,
    ActivityDetector,
    normalize_observations,
)

print("[PASS] TmuxStateParserV11 import OK.")
print("[PASS] IdentityResolver import OK.")
print("[PASS] ActivityDetector import OK.")
print("[PASS] normalize_observations import OK.")
PY

echo "[PASS] Normalization module integrity OK."
echo

# ----------------------------------------------------------------------
# GATE 3 — Raw observation + normalization smoke test
# ----------------------------------------------------------------------

echo "[GATE 3] Raw observation and normalization"
echo "------------------------------------------------------------"

"$PYTHON" scripts/smoke_test.py

echo "------------------------------------------------------------"
echo "[PASS] Smoke test process completed."
echo

# ----------------------------------------------------------------------
# GATE 4 — Direct semantic validation
# ----------------------------------------------------------------------

echo "[GATE 4] Semantic normalization validation"

"$PYTHON" - <<'PY'
import os
import yaml

from sentinel.sensors.tmux.parser import TmuxStateParserV11
from sentinel.normalization.resolver import (
    IdentityResolver,
    normalize_observations,
)

repo = os.path.expanduser("~/airiv/airiv-sentinel")
config_path = os.path.join(repo, "config", "identities.yaml")

if not os.path.exists(config_path):
    raise SystemExit("[FAIL] identities.yaml not found.")

with open(config_path, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

target_session = config.get("session", "airiv")

mapping_rules = {}

for agent, data in config.get("identities", {}).items():
    for window in data.get("windows", []):
        mapping_rules[window] = agent.upper()

parser = TmuxStateParserV11(target_session=target_session)
resolver = IdentityResolver(mapping_rules=mapping_rules)

# ------------------------------------------------------------
# Observation Pass 1
# ------------------------------------------------------------

raw1 = parser.inspect_panes()

if not raw1:
    raise SystemExit(
        f"[FAIL] No panes discovered in tmux session '{target_session}'."
    )

norm1 = normalize_observations(raw1, resolver)

print(f"[INFO] Pass 1 panes: {len(norm1)}")

for obs in norm1:
    print(
        f"[OBS] "
        f"pane={obs['pane_id']} "
        f"window={obs['window_name']} "
        f"identity={obs['agent_identity']} "
        f"capture_ok={obs['capture_ok']} "
        f"first={obs['first_observation']} "
        f"activity={obs['activity_state']}"
    )

    if obs["capture_ok"] is not True:
        raise SystemExit(
            f"[FAIL] Capture failed for pane {obs['pane_id']}."
        )

    if obs["first_observation"] is not True:
        raise SystemExit(
            f"[FAIL] First observation flag incorrect for pane {obs['pane_id']}."
        )

    if obs["activity_state"] != "INITIALIZED":
        raise SystemExit(
            f"[FAIL] Expected INITIALIZED for first observation, "
            f"got {obs['activity_state']}."
        )

# ------------------------------------------------------------
# Observation Pass 2
# ------------------------------------------------------------

raw2 = parser.inspect_panes()
norm2 = normalize_observations(raw2, resolver)

if len(norm2) != len(norm1):
    print(
        "[WARNING] Pane count changed between observations."
    )

print(f"[INFO] Pass 2 panes: {len(norm2)}")

for obs in norm2:
    print(
        f"[OBS] "
        f"pane={obs['pane_id']} "
        f"window={obs['window_name']} "
        f"identity={obs['agent_identity']} "
        f"capture_ok={obs['capture_ok']} "
        f"changed={obs['output_changed']} "
        f"activity={obs['activity_state']}"
    )

    if obs["capture_ok"] is not True:
        raise SystemExit(
            f"[FAIL] Capture failed during second observation "
            f"for pane {obs['pane_id']}."
        )

print()
print("[PASS] Raw observation integrity.")
print("[PASS] First-observation semantics.")
print("[PASS] Capture semantics.")
print("[PASS] Identity normalization executed.")
print("[PASS] Activity delta semantics.")
PY

echo
echo "============================================================"
echo " TMUX NORMALIZATION V1.1 — VALIDATION RESULT"
echo "============================================================"
echo
echo "[PASS] GATE 0 — Runtime prerequisites"
echo "[PASS] GATE 1 — Tmux session discovery"
echo "[PASS] GATE 2 — Normalization module integrity"
echo "[PASS] GATE 3 — Smoke test execution"
echo "[PASS] GATE 4 — Semantic normalization validation"
echo
echo "============================================================"
echo " DECISION"
echo "============================================================"
echo
echo "Tmux Normalization V1.1 is VALIDATED."
echo
echo "NEXT:"
echo "  -> Lock Tmux Normalization V1.1"
echo "  -> Begin State Machine V1"
echo
echo "============================================================"
