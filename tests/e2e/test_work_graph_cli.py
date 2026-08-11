from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "vnext" / "simple_work_graph.json"


def _run(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def test_work_graph_plan_status_and_dry_run(tmp_path: Path) -> None:
    init = _run(ROOT, ["init", str(tmp_path), "--name", "smoke", "--privacy", "abstract", "--tier", "auto"])
    assert init.returncode == 0, init.stderr

    planned = _run(tmp_path, ["plan", "--from-json", str(FIXTURE), "--json"])
    assert planned.returncode == 0, planned.stderr
    assert json.loads(planned.stdout)["id"] == "graph_smoke"

    status = _run(tmp_path, ["status", "--graph", "graph_smoke", "--json"])
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout)["nodes"][0]["id"] == "node_smoke"

    dry_run = _run(tmp_path, ["run", "--graph", "graph_smoke", "--dry-run"])
    assert dry_run.returncode == 0, dry_run.stderr
    payload = json.loads(dry_run.stdout)
    assert payload["dry_run"] is True
    assert payload["selected"][0]["requires"] == ["test.echo"]
    assert payload["selected"][0]["policy"] == "not_invoked"
