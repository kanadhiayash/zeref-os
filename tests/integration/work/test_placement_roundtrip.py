from __future__ import annotations

import json

from shiroe.work.compiler import compile_work_graph
from shiroe.work.schema import Placement
from shiroe.work.store import WorkStore


def test_work_store_round_trips_node_placement(tmp_path) -> None:
    graph = compile_work_graph(
        {
            "id": "g1",
            "objective": "remote",
            "nodes": [
                {
                    "id": "n1",
                    "kind": "task",
                    "objective": "run remote check",
                    "placement": {"mode": "node", "node_id": "node_worker"},
                    "metadata": {},
                }
            ],
        }
    )

    store = WorkStore(tmp_path)
    store.create(graph)

    loaded = store.get("g1").nodes[0]
    stored_json = store.conn.execute(
        "SELECT placement_json FROM work_nodes WHERE id='n1'"
    ).fetchone()[0]

    assert loaded.placement == Placement(mode="node", node_id="node_worker")
    assert json.loads(stored_json) == {"mode": "node", "node_id": "node_worker"}
