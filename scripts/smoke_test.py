import os
import sys
import yaml

sys.path.insert(
    0,
    os.path.expanduser("~/airiv/airiv-sentinel"),
)

from sentinel.sensors.tmux.parser import TmuxStateParserV11
from sentinel.normalization.resolver import (
    IdentityResolver,
    normalize_observations,
)


def run_smoke_test():
    config_path = os.path.expanduser(
        "~/airiv/airiv-sentinel/config/identities.yaml"
    )

    if not os.path.exists(config_path):
        print(f"[ERROR] Configuration not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    mapping_rules = {}

    for agent, data in config.get("identities", {}).items():
        for window in data.get("windows", []):
            mapping_rules[window] = agent.upper()

    target_session = config.get("session", "airiv")

    print(
        f"[*] Tmux session: {target_session}"
    )

    parser = TmuxStateParserV11(
        target_session=target_session
    )

    resolver = IdentityResolver(
        mapping_rules=mapping_rules
    )

    print("[*] Pass 1")

    raw_1 = parser.inspect_panes()
    norm_1 = normalize_observations(
        raw_1,
        resolver,
    )

    if not norm_1:
        print(
            f"[WARNING] No panes found in "
            f"tmux session '{target_session}'."
        )
    else:
        for obs in norm_1:
            print(
                f"    Pane={obs['pane_id']} "
                f"Window={obs['window_name']} "
                f"Identity={obs['agent_identity']} "
                f"Activity={obs['activity_state']} "
                f"CaptureOK={obs['capture_ok']}"
            )

    print("[OK] Source smoke test completed")


if __name__ == "__main__":
    run_smoke_test()
