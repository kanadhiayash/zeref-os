from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from shiroe.capabilities.inspection import inspect_source
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


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
        timeout=10,
    )


def _assert_ok(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout


def _seed_cli_capability(root: Path, capability_id: str = "test.echo") -> None:
    script = root / "capabilities" / "test_echo" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'message': 'ok'}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    digest = inspect_source(script).digest
    store = CapabilityStore(root)
    try:
        store.upsert_capability(
            capability_id=capability_id,
            name="Test Echo",
            type_="script",
            lifecycle="active",
            digest=digest,
            manifest={
                "schema": "shiroe.capability/v1",
                "id": capability_id,
                "name": "Test Echo",
                "type": "script",
                "version": "1.0.0",
                "source": {"kind": "local-file", "location": str(script)},
                "entrypoint": {"adapter": "cli", "command": [str(script)]},
                "requires": {},
            },
            source_kind="local-file",
            source_location=str(script),
        )
    finally:
        store.close()


def _allow_subprocess_policy(root: Path) -> None:
    policy_dir = root / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True, exist_ok=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess"]}),
        encoding="utf-8",
    )


def _seed_approval_graph(root: Path) -> str:
    graph = compile_work_graph(
        {
            "id": "graph_publish",
            "objective": "Publish release with human approval",
            "nodes": [
                {
                    "id": "approval_publish",
                    "kind": "approval",
                    "objective": "Approve publish",
                    "approval_required": True,
                    "metadata": {"scope": {"tag": "v1"}},
                },
                {
                    "id": "publish",
                    "kind": "task",
                    "objective": "Publish",
                    "requires": ["test.echo"],
                },
            ],
            "edges": [{"from": "approval_publish", "to": "publish"}],
        }
    )
    store = WorkStore(root)
    try:
        store.create(graph)
    finally:
        store.close()
    service = ApprovalService(root)
    try:
        req = service.request(
            approval_type="action",
            requested_action="publish v1",
            scope={"tag": "v1"},
            reason="fresh project publish gate",
            risk="high",
            graph_id=graph.id,
            node_id="approval_publish",
            action_kind="publish",
        )
    finally:
        service.close()
    return req.id


def test_fresh_project_lifecycle(tmp_path: Path) -> None:
    _assert_ok(_run(ROOT, ["init", str(tmp_path), "--name", "smoke", "--privacy", "abstract", "--tier", "auto"]))
    _seed_cli_capability(tmp_path)
    _allow_subprocess_policy(tmp_path)

    status = json.loads(_assert_ok(_run(tmp_path, ["status", "--json"])))
    assert status["project_root"] == str(tmp_path)

    planned = json.loads(_assert_ok(_run(tmp_path, ["plan", "--from-json", str(GRAPH), "--json"])))
    assert planned == {"id": "graph_smoke", "nodes": 1, "status": "draft"}

    graph_status = json.loads(_assert_ok(_run(tmp_path, ["status", "--graph", "graph_smoke", "--json"])))
    assert graph_status["graph"]["id"] == "graph_smoke"
    assert graph_status["nodes"][0]["id"] == "node_smoke"

    executed = json.loads(_assert_ok(_run(tmp_path, ["run", "--graph", "graph_smoke", "--json"])))
    assert executed["status"] == "completed"
    assert executed["completed"] == ["node_smoke"]

    approval_id = _seed_approval_graph(tmp_path)
    paused = json.loads(_assert_ok(_run(tmp_path, ["run", "--graph", "graph_publish", "--json"])))
    assert paused["status"] == "paused"
    assert paused["blocked"] == ["approval_publish"]
    assert paused["reason"] == "approval"
    pending_handoff = json.loads(_assert_ok(_run(tmp_path, ["handoff", "human", "--graph", "graph_publish", "--json"])))
    assert pending_handoff["packet"]["pending_approvals"][0]["id"] == approval_id

    approved = json.loads(_assert_ok(_run(
        tmp_path,
        [
            "approve",
            "decide",
            approval_id,
            "--decision",
            "approved",
            "--reason",
            "human confirmed v1",
            "--json",
        ],
    )))
    assert approved["status"] == "approved"
    service = ApprovalService(tmp_path)
    try:
        service.assert_current(approval_id, current_scope={"tag": "v1"})
    finally:
        service.close()

    resumed = json.loads(_assert_ok(_run(tmp_path, ["run", "--graph", "graph_publish", "--json"])))
    assert resumed["status"] == "completed"
    assert resumed["completed"] == ["publish"]
    publish_status = json.loads(_assert_ok(_run(tmp_path, ["status", "--graph", "graph_publish", "--json"])))
    assert {node["id"]: node["status"] for node in publish_status["nodes"]} == {
        "approval_publish": "completed",
        "publish": "completed",
    }

    written = json.loads(_assert_ok(_run(tmp_path, ["memory", "write", "--from", str(MEMORY), "--json"])))
    memory_id = written["id"]
    recalled = json.loads(_assert_ok(_run(tmp_path, ["memory", "recall", "single node smoke", "--json"])))
    assert recalled["hits"][0]["record"]["id"] == memory_id

    verified = json.loads(_assert_ok(_run(tmp_path, ["verify", "--graph", "graph_smoke", "--json"])))
    assert verified["status"] == "pass"

    views_dir = tmp_path / "memory" / "views"
    _assert_ok(_run(tmp_path, ["memory", "views"]))
    before = sorted(path.name for path in views_dir.glob("*.md"))
    assert before
    shutil.rmtree(views_dir)
    rebuilt = json.loads(_assert_ok(_run(tmp_path, ["state", "rebuild", "--json"])))
    after = sorted(path.name for path in views_dir.glob("*.md"))
    assert after == before
    assert rebuilt["replayed"] >= 1

    handoff = json.loads(_assert_ok(_run(tmp_path, ["handoff", "human", "--graph", "graph_publish", "--json"])))
    packet = handoff["packet"]
    assert packet["graph"]["id"] == "graph_publish"
    assert packet["graph"]["version"] == 1
    assert packet["pending_approvals"] == []
    assert packet["active_decisions"][0]["id"] == memory_id

    state = json.loads(_assert_ok(_run(tmp_path, ["state", "verify", "--json"])))
    assert state["status"] == "pass"
    assert state["chain"] == "ok"
