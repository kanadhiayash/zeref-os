from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _run(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def test_doctor_reports_runtime_health_only(tmp_path: Path) -> None:
    assert _run(ROOT, ["init", str(tmp_path), "--name", "doctor", "--privacy", "abstract", "--tier", "auto"]).returncode == 0
    result = _run(tmp_path, ["doctor", "--json"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    names = {check["name"] for check in payload["checks"]}
    assert {"canonical_state", "hash_chain", "policy_stack", "capability_store", "adapters"} <= names
    assert "claim_gate" not in names
    assert "release" not in result.stdout.lower()
    assert "benchmark" not in result.stdout.lower()
