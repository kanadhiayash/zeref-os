#!/usr/bin/env python3
"""Fail if critical-package line% or branch% falls under its own threshold.

coverage.py's `--fail-under` only checks one combined (line+branch) number,
which can hide a low branch% behind a high line%. This reads a `coverage
json` report and asserts line and branch coverage independently.

Usage:
    coverage json -o /tmp/cov.json --include='shiroe/policy/*,...'
    python3 scripts/check-critical-coverage.py /tmp/cov.json --min-line 90 --min-branch 80
"""
from __future__ import annotations

import argparse
import json
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", help="Path to a `coverage json` report")
    parser.add_argument("--min-line", type=float, default=90.0)
    parser.add_argument("--min-branch", type=float, default=80.0)
    args = parser.parse_args()

    with open(args.json_path, encoding="utf-8") as f:
        totals = json.load(f)["totals"]

    num_statements = totals["num_statements"]
    num_branches = totals.get("num_branches", 0)
    line_pct = 100.0 * totals["covered_lines"] / num_statements if num_statements else 100.0
    branch_pct = 100.0 * totals["covered_branches"] / num_branches if num_branches else 100.0

    print(f"critical line coverage:   {line_pct:.2f}% (threshold {args.min_line:.1f}%)")
    print(f"critical branch coverage: {branch_pct:.2f}% (threshold {args.min_branch:.1f}%)")

    failed = False
    if line_pct < args.min_line:
        print(f"FAIL: line coverage {line_pct:.2f}% < {args.min_line:.1f}%")
        failed = True
    if branch_pct < args.min_branch:
        print(f"FAIL: branch coverage {branch_pct:.2f}% < {args.min_branch:.1f}%")
        failed = True

    if failed:
        return 1
    print("PASS: critical line and branch coverage both meet threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
