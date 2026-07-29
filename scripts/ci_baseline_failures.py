#!/usr/bin/env python3
"""Print the set of failing/erroring test ids, one per line.

Used to capture the merge base's failures so CI can compare against them.
Shares its parser with ci_regression_check so the two cannot drift apart.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ci_regression_check import run_suite

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "tests/"
    for t in sorted(run_suite(target)):
        print(t)
