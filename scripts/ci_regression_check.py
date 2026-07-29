#!/usr/bin/env python3
"""Fail CI only when a change ADDS test failures.

Why this exists
---------------
The test step used to run `pytest tests/ ... || true`, so it could never fail.
Every green tick on every pull request meant nothing, and contributors were
reporting "all tests pass" in good faith on the strength of it.

Deleting the `|| true` is not usable on its own: main currently carries a large
number of pre-existing failures, so every pull request would go red on work its
author never touched. That is a different kind of useless.

So this compares failure *sets* rather than counts. It runs the suite twice,
once on the merge base and once on the pull request head, and fails only if a
test that passed on the base now fails. Pre-existing failures stay visible in
the log without blocking anyone, and a pull request that fixes one is reported
as an improvement.

Counts are deliberately not the signal: the same suite can report 148 or 149
depending on ordering, so a count comparison is flaky where a set comparison is
stable.
"""

from __future__ import annotations

import re
import subprocess
import sys

# "FAILED tests/test_x.py::test_y - AssertionError: ..." / "ERROR tests/test_z.py"
_OUTCOME = re.compile(r"^(FAILED|ERROR)\s+(\S+?)(?:\s+-.*)?$", re.M)


def run_suite(target: str) -> set[str]:
    """Run pytest and return the set of failing/erroring test ids.

    A crash of pytest itself is not the same as a test failure, and must not be
    silently reported as an empty failure set, which would look like success.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", target, "-q", "--no-header",
         "-p", "no:cacheprovider", "--continue-on-collection-errors"],
        capture_output=True, text=True,
    )
    out = proc.stdout + proc.stderr
    ids = {m.group(2) for m in _OUTCOME.finditer(out)}
    # pytest: 0 = all passed, 1 = tests failed, 2 = interrupted, 5 = none collected.
    if proc.returncode not in (0, 1) and not ids:
        print(f"::error::pytest exited {proc.returncode} without reporting failures; "
              f"treating as broken rather than clean")
        print(out[-4000:])
        sys.exit(2)
    return ids


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: ci_regression_check.py <base-failures-file> <target-dir>")
        return 2
    base_file, target = sys.argv[1], sys.argv[2]
    with open(base_file) as fh:
        base = {ln.strip() for ln in fh if ln.strip()}

    head = run_suite(target)
    new = sorted(head - base)
    fixed = sorted(base - head)

    print(f"baseline failing: {len(base)}")
    print(f"head failing:     {len(head)}")

    if fixed:
        print(f"\nfixed by this change ({len(fixed)}):")
        for t in fixed:
            print(f"  + {t}")

    if new:
        print(f"\n::error::this change adds {len(new)} new test failure(s):")
        for t in new:
            print(f"  - {t}")
        return 1

    print("\nno new failures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
