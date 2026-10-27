"""에이전트가 작업 공간 안에서 돌리는 검사기.

python -m character_factory_poc.checks.cli <stage> <workspace>
"""

from __future__ import annotations

import sys
from pathlib import Path

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.checks.registry import run_checks


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) < 2:
        print("usage: cfp-check <stage> <workspace>", file=sys.stderr)
        return 2
    problems = run_checks(args[0], Path(args[1]))
    if problems:
        print("FAIL")
        for p in problems:
            print(f"- {p}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
