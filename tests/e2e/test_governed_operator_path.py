"""RED gate for the governed operator path (Task A7).

Every runtime state transition happens through the public CLI. No test
helper touches CapabilityStore, WorkStore or ApprovalService directly.
Confirms:

* Fresh project starts with zero capabilities.
* ``shiroe capability onboard`` is the sole compact composite command.
* Capability cannot execute before real human approval.
* Approval request auto-created by onboard and surfaced via ``approve list``.
* ``approve decide`` unlocks the gate.
* ``plan`` + ``run`` produce a real filesystem output.
* Event history contains the run/step/approval/capability trail.
* Deleting rebuildable projection tables and calling ``state rebuild``
  reconstructs the exercised domains from JSONL.
* Semantic before/after digest is equal for every exercised domain.

Fails on 451a74d because ``capability onboard`` does not exist, the
Work Graph and approval domains do not emit events, and ``state rebuild``
does not report per-domain status. Turns GREEN once Tranche A lands.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
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
        timeout=30,
    )


def _ok(result: subprocess.CompletedProcess) -> str:
    assert result.returncode == 0, (
        f"exit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return result.stdout


def _fail(result: subprocess.CompletedProcess) -> None:
    assert result.returncode != 0, f"expected non-zero exit, got 0\nstdout={result.stdout}"


def _write_indexer_fixture(root: Path) -> Path:
    """One disposable project script; user's input, not internal seeding."""
    script = root / "capabilities" / "notes_indexer" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "from pathlib import Path\n"
        "out = Path('research-index.md')\n"
        "out.write_text('# Research index\\n\\nseed: ok\\n', encoding='utf-8')\n"
        "print(json.dumps({'wrote': str(out), 'ok': True}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def _write_governed_graph(root: Path, capability_id: str) -> Path:
    graph_path = root / "graphs" / "index.json"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps(
            {
                "id": "graph_index",
                "objective": "Regenerate the research index via governed capability",
                "nodes": [
                    {
                        "id": "run_indexer",
                        "kind": "task",
                        "objective": "Invoke notes_indexer",
                        "requires": [capability_id],
                    }
                ],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )
    return graph_path


def _semantic_digest(state_db: Path) -> dict[str, str]:
    """Domain-scoped semantic digest over current projection tables.

    Volatile fields (autoincrement PKs, non-event timestamps) excluded.
    """
    conn = sqlite3.connect(state_db)
    try:
        conn.row_factory = sqlite3.Row
        digests: dict[str, str] = {}
        for domain, sql in (
            (
                "memory",
                "SELECT id, kind, title, claim, owner, status, archived "
                "FROM memory_records ORDER BY id",
            ),
            (
                "capabilities",
                "SELECT id, name, type, lifecycle, current_digest "
                "FROM capabilities ORDER BY id",
            ),
            (
                "approvals",
                "SELECT id, approval_type, status, scope_digest, decided_by, decision_reason "
                "FROM approval_requests ORDER BY id",
            ),
            (
                "work_graphs",
                "SELECT id, objective, status FROM work_graphs ORDER BY id",
            ),
            (
                "work_nodes",
                "SELECT id, graph_id, status, kind, output_json "
                "FROM work_nodes ORDER BY graph_id, id",
            ),
            (
                "work_attempts",
                "SELECT graph_id, node_id, attempt, capability_id, state, input_digest, "
                "output_digest, error, usage_json FROM work_attempts "
                "ORDER BY graph_id, node_id, attempt",
            ),
        ):
            rows = conn.execute(sql).fetchall()
            h = hashlib.sha256()
            for row in rows:
                h.update(repr(tuple(row)).encode("utf-8"))
            digests[domain] = h.hexdigest()
        return digests
    finally:
        conn.close()


def _delete_rebuildable_projections(state_db: Path) -> None:
    """FK-safe wipe of every declared rebuildable domain."""
    conn = sqlite3.connect(state_db)
    try:
        for table in (
            "work_attempts",
            "work_edges",
            "work_nodes",
            "work_graphs",
            "approval_advice",
            "approval_requests",
            "capability_permissions",
            "capability_versions",
            "capabilities",
            "memory_events",
            "memory_sources",
            "memory_records",
        ):
            try:
                conn.execute(f"DELETE FROM {table}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()


def test_governed_operator_path(tmp_path: Path) -> None:
    _ok(_run(ROOT, ["init", str(tmp_path), "--name", "governed", "--privacy", "abstract"]))
    state_db = tmp_path / "memory" / "state" / "shiroe.sqlite"

    caps_before = json.loads(_ok(_run(tmp_path, ["capability", "list", "--json"])))
    assert caps_before == [], f"fresh project must start with zero capabilities, got {caps_before}"

    script = _write_indexer_fixture(tmp_path)

    # A3: `capability onboard` composite command drives inspection,
    # discovery, quarantine, inspected transitions, and creates the human
    # approval request bound to (capability_id, digest).
    onboarded = json.loads(_ok(_run(tmp_path, ["capability", "onboard", str(script), "--json"])))
    capability_id = onboarded["capability_id"]
    approval_id = onboarded["approval_id"]
    digest = onboarded["digest"]
    assert capability_id
    assert approval_id
    assert digest.startswith("sha256:")
    assert onboarded["lifecycle"] == "inspected"

    # Gate must fail-closed before approval.
    _fail(_run(tmp_path, ["capability", "gate", capability_id]))

    # Approval request surfaces via public CLI, not manufactured internally.
    pending = json.loads(_ok(_run(tmp_path, ["approve", "list", "--json"])))
    pending_ids = [row["id"] for row in pending]
    assert approval_id in pending_ids, f"expected {approval_id} in {pending_ids}"

    # Real human decision authorizes.
    _ok(_run(tmp_path, [
        "approve", "decide", approval_id,
        "--decision", "approved",
        "--reason", "governed operator test",
        "--json",
    ]))

    # Gate passes after approval.
    _ok(_run(tmp_path, ["capability", "gate", capability_id]))

    # Plan / dry-run / run through CLI. Real filesystem output.
    graph_path = _write_governed_graph(tmp_path, capability_id)
    planned = json.loads(_ok(_run(tmp_path, ["plan", "--from-json", str(graph_path), "--json"])))
    assert planned["id"] == "graph_index"

    dry = json.loads(_ok(_run(tmp_path, ["run", "--graph", "graph_index", "--dry-run", "--json"])))
    assert dry.get("dry_run") is True

    executed = json.loads(_ok(_run(tmp_path, ["run", "--graph", "graph_index", "--json"])))
    assert executed["status"] == "completed", executed
    output = script.parent / "research-index.md"
    assert output.exists(), f"expected {output} to exist after governed run"

    verified = json.loads(_ok(_run(tmp_path, ["verify", "--graph", "graph_index", "--json"])))
    assert verified["status"] == "pass"

    conn = sqlite3.connect(state_db)
    try:
        attempt_before = conn.execute(
            "SELECT graph_id, node_id, attempt, capability_id, state, input_digest, "
            "output_digest, error, usage_json FROM work_attempts "
            "ORDER BY graph_id, node_id, attempt"
        ).fetchall()
    finally:
        conn.close()
    assert len(attempt_before) == 1
    assert attempt_before[0][4] == "completed"

    # Canonical event history contains the exercised domains.
    conn = sqlite3.connect(state_db)
    try:
        event_types = [
            row[0]
            for row in conn.execute(
                "SELECT event_type FROM memory_events ORDER BY timestamp"
            ).fetchall()
        ]
    finally:
        conn.close()
    for required in (
        "capability.discovered", "approval.requested", "approval.decided",
        "run.created", "attempt.started", "attempt.completed",
    ):
        assert required in event_types, f"missing {required} in emitted events: {event_types}"

    # Semantic digest BEFORE rebuild.
    before = _semantic_digest(state_db)

    # Wipe rebuildable projection tables; rebuild from JSONL alone.
    _delete_rebuildable_projections(state_db)
    rebuilt = json.loads(_ok(_run(tmp_path, ["state", "rebuild", "--json"])))
    assert "domains" in rebuilt, f"state rebuild must report per-domain status, got {rebuilt}"
    for domain in ("capabilities", "approvals", "work_projection"):
        assert rebuilt["domains"].get(domain) == "rebuilt", rebuilt
    assert rebuilt["domains"].get("memory") in {"rebuilt", "not_exercised"}, rebuilt

    after = _semantic_digest(state_db)
    assert after == before, f"semantic digest drift after rebuild: {before} != {after}"

    # Capability approval and attempt history remain executable/replayable
    # after rebuilding current projections from JSONL alone.
    _ok(_run(tmp_path, ["capability", "gate", capability_id]))
    conn = sqlite3.connect(state_db)
    try:
        capability_after = conn.execute(
            "SELECT lifecycle, current_digest FROM capabilities WHERE id=?",
            (capability_id,),
        ).fetchone()
        attempt_after = conn.execute(
            "SELECT graph_id, node_id, attempt, capability_id, state, input_digest, "
            "output_digest, error, usage_json FROM work_attempts "
            "ORDER BY graph_id, node_id, attempt"
        ).fetchall()
    finally:
        conn.close()
    assert capability_after == ("approved", digest)
    assert attempt_after == attempt_before

    _ok(_run(tmp_path, ["state", "verify", "--json"]))
