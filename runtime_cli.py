from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import TextIO

from runtime import Runtime


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    args = tuple(sys.argv[1:] if argv is None else argv)
    output = sys.stdout if stdout is None else stdout
    if len(args) != 1:
        print("usage: runtime_cli.py <queue-path>", file=output)
        return 1

    report = Runtime(args[0]).run_once()
    print(
        f"STATUS={'PASS' if report.status == 'success' else 'FAIL'} "
        f"TASK_ID={report.task_id or '-'} "
        f"TASK_NAME={report.task_name or '-'} "
        f"VERIFICATION={report.verification or '-'}",
        file=output,
    )
    return 0 if report.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
