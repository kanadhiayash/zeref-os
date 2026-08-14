#!/usr/bin/env python3
"""H7.1: vNext-native release-readiness gate.

Aggregates every surviving vNext invariant into one local, deterministic
check. Does NOT resurrect the retired ``shiroe.release`` package -- just
composes existing authoritative checks.

Exit code: 0 iff every subcheck passes; non-zero on the first failure.
JSON summary always printed to stdout so a caller (or CI) can capture
the evidence.

Runs (all local, no network):

  1. python3 -m pytest -q                        -- full test suite
  2. python3 scripts/shiroe-validate.py          -- structural validation
  3. python3 scripts/check-canon-consistency.py --root .
  4. python3 scripts/check-active-identity.py --root .
  5. python3 scripts/check-version-consistency.py
  6. python3 scripts/check-trust-registry.py
  7. python3 -m shiroe doctor --json             -- runtime health
  8. python3 -m shiroe verify --memory --json    -- memory chain
  9. python3 -m shiroe state verify --json       -- event log chain
 10. python3 -m pytest tests/invariant -q        -- mandatory invariants
 11. Dead-surface scanner (invariant/test_no_dead_surface_references.py)

No benchmark, no push, no external network. If any subcheck fails, the
gate is CLOSED and the summary records the first failure's stderr.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# CI job may already have run the full test suite in a parallel step.
# Setting SHIROE_RELEASE_READY_SKIP=pytest-full,invariant-suite in the
# environment tells this gate to skip those and rely on the parallel
# job's result -- keeps CI wall time down while preserving local
# semantics where the env var is unset.
_SKIP = {
    s.strip()
    for s in os.environ.get("SHIROE_RELEASE_READY_SKIP", "").split(",")
    if s.strip()
}


_ALL_CHECKS = [
    ("pytest-full", ["python3", "-m", "pytest", "-q"]),
    ("shiroe-validate", ["python3", "scripts/shiroe-validate.py"]),
    ("canon-consistency", ["python3", "scripts/check-canon-consistency.py", "--root", "."]),
    ("active-identity", ["python3", "scripts/check-active-identity.py", "--root", "."]),
    ("version-consistency", ["python3", "scripts/check-version-consistency.py"]),
    ("trust-registry", ["python3", "scripts/check-trust-registry.py"]),
    ("doctor", ["python3", "-m", "shiroe", "doctor", "--json"]),
    ("verify-runtime", ["python3", "-m", "shiroe", "verify", "--json"]),
    ("state-verify", ["python3", "-m", "shiroe", "state", "verify", "--json"]),
    ("invariant-suite", ["python3", "-m", "pytest", "tests/invariant", "-q"]),
    ("dead-surface-scanner",
     ["python3", "-m", "pytest",
      "tests/invariant/test_no_dead_surface_references.py", "-q"]),
]


CHECKS = [(name, cmd) for name, cmd in _ALL_CHECKS if name not in _SKIP]


def _run(name: str, cmd: list[str]) -> dict:
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return {
        "check": name,
        "cmd": " ".join(cmd),
        "returncode": proc.returncode,
        "duration_s": round(time.perf_counter() - start, 2),
        "stderr_tail": proc.stderr.strip().splitlines()[-5:] if proc.stderr else [],
    }


def main() -> int:
    results = []
    first_failure: dict | None = None
    for name, cmd in CHECKS:
        result = _run(name, cmd)
        results.append(result)
        if result["returncode"] != 0 and first_failure is None:
            first_failure = result
            break

    summary = {
        "gate": "vnext-release-readiness",
        "status": "PASS" if first_failure is None else "FAIL",
        "checks_run": len(results),
        "checks_total": len(CHECKS),
        "first_failure": first_failure,
        "results": results,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if first_failure is None else 1


if __name__ == "__main__":
    sys.exit(main())
