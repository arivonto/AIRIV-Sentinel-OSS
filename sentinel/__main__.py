"""Run AIRIV Sentinel or a Phase 1 text mission command."""

import sys

from sentinel.mission_cli import main as mission_cli_main
from sentinel.worker.entrypoint import main


if __name__ == "__main__":
    if sys.argv[1:2] == ["mission"]:
        raise SystemExit(mission_cli_main())
    raise SystemExit(main())
