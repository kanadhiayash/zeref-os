from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "tests" / "fixtures" / "vnext" / "simple_work_graph.json"
MEMORY = ROOT / "tests" / "fixtures" / "vnext" / "simple_memory.json"


def _run(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )


def test_memory_verify_and_handoff_cli(tmp_path: Path) -> None:
    assert _run(ROOT, ["init", str(tmp_path), "--name", "handoff", "--privacy", "abstract"]).returncode == 0
    assert _run(tmp_path, ["plan", "--from-json", str(GRAPH)]).returncode == 0

    written = _run(tmp_path, ["memory", "write", "--from", str(MEMORY), "--json"])
    assert written.returncode == 0, written.stderr
    memory_id = json.loads(written.stdout)["id"]

    recall = _run(tmp_path, ["memory", "recall", "single node smoke", "--json"])
    assert recall.returncode == 0, recall.stderr
    assert json.loads(recall.stdout)["hits"][0]["record"]["id"] == memory_id

    verify_graph = _run(tmp_path, ["verify", "--graph", "graph_smoke", "--json"])
    assert verify_graph.returncode == 0, verify_graph.stderr
    assert json.loads(verify_graph.stdout)["status"] == "pass"

    verify_memory = _run(tmp_path, ["verify", "--memory", memory_id, "--json"])
    assert verify_memory.returncode == 0, verify_memory.stderr
    assert json.loads(verify_memory.stdout)["status"] == "pass"

    handoff = _run(tmp_path, ["handoff", "human", "--graph", "graph_smoke", "--json"])
    assert handoff.returncode == 0, handoff.stderr
    packet = json.loads(handoff.stdout)["packet"]
    assert packet["graph"]["id"] == "graph_smoke"
    assert packet["active_decisions"][0]["id"] == memory_id
