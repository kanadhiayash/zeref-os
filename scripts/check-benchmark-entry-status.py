#!/usr/bin/env python3
"""Check benchmark-entry status without running benchmarks."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "docs" / "evidence" / "benchmark-entry-audit.md"


def main() -> int:
    if not AUDIT.is_file():
        print(json.dumps({"status": "FAIL", "reason": "benchmark-entry audit missing"}))
        return 1
    text = AUDIT.read_text(encoding="utf-8")
    status_closed = "## Result: **CLOSED**" in text and "Until then: **CLOSED**" in text
    no_run = "no\nbenchmark run was started" in text or "no benchmark run was started" in text
    no_claim = "Do not claim benchmark leadership or entry." in text
    ok = status_closed and no_run and no_claim
    print(json.dumps({
        "check": "benchmark-entry-status",
        "status": "PASS" if ok else "FAIL",
        "result": "CLOSED" if status_closed else "UNKNOWN",
        "benchmark_run_started": not no_run,
        "claim_guard": no_claim,
    }, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
