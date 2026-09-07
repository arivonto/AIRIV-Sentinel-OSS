"""Run AIRIV Sentinel in the foreground with python -m sentinel."""

from sentinel.worker.entrypoint import main


if __name__ == "__main__":
    raise SystemExit(main())
