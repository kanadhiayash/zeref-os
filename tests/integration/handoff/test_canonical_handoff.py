from __future__ import annotations

import shutil
from pathlib import Path

from shiroe.handoff.compiler import compile_handoff
from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService
from shiroe.memory.views import render_views
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


def test_handoff_compiles_from_canonical_state_without_generated_views(tmp_path: Path) -> None:
    graph = compile_work_graph(
        {
            "id": "graph_smoke",
            "objective": "Complete a single node smoke graph.",
            "nodes": [
                {
                    "id": "single-node",
                    "kind": "task",
                    "objective": "Prove canonical handoff source.",
                    "requires": [],
                    "risk": "low",
                    "metadata": {"files": ["tests/fixtures/vnext/simple_work_graph.json"]},
                }
            ],
            "success_criteria": ["handoff contains canonical graph and memory state"],
        }
    )
    WorkStore(tmp_path).create(graph)
    decision = MemoryService(tmp_path).write(
        MemoryWrite(
            kind="decision",
            title="Canonical handoff source",
            claim="Handoff packets read Work Graph and memory from canonical SQLite.",
            source_refs=("tests/integration/handoff/test_canonical_handoff.py",),
            evidence_grade="A",
            privacy_class="public",
        )
    )
    render_views(tmp_path)
    shutil.rmtree(tmp_path / "memory" / "views")

    packet = compile_handoff(tmp_path, graph_id="graph_smoke", target="human")

    assert packet["packet"]["graph"]["id"] == "graph_smoke"
    assert packet["packet"]["pending_nodes"][0]["id"] == "single-node"
    assert packet["packet"]["active_decisions"][0]["id"] == decision.id
    assert packet["packet"]["relevant_files"] == [
        "tests/fixtures/vnext/simple_work_graph.json",
        "tests/integration/handoff/test_canonical_handoff.py",
    ]
