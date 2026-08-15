from __future__ import annotations

import pytest

from shiroe.work.compiler import WorkGraphError, compile_work_graph
from shiroe.work.schema import Placement, WorkNode


def test_placement_defaults_to_local_without_node() -> None:
    placement = Placement()

    assert placement.mode == "local"
    assert placement.node_id is None


def test_node_placement_requires_node_id() -> None:
    with pytest.raises(ValueError, match="requires node_id"):
        Placement(mode="node")


def test_local_placement_cannot_name_node_id() -> None:
    with pytest.raises(ValueError, match="cannot name node_id"):
        Placement(mode="local", node_id="node_abc")


def test_work_node_coerces_placement_dict() -> None:
    node = WorkNode(
        id="n1",
        graph_id="g1",
        kind="task",
        objective="run remote check",
        placement={"mode": "node", "node_id": "node_worker"},
    )

    assert node.placement == Placement(mode="node", node_id="node_worker")


def test_compile_reads_placement_as_typed_field() -> None:
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
                    "metadata": {"purpose": "remote"},
                }
            ],
        }
    )

    node = graph.nodes[0]
    assert node.placement == Placement(mode="node", node_id="node_worker")
    assert node.metadata == {"purpose": "remote"}


def test_compile_rejects_placement_hidden_in_metadata() -> None:
    with pytest.raises(WorkGraphError, match="top-level placement"):
        compile_work_graph(
            {
                "id": "g1",
                "objective": "remote",
                "nodes": [
                    {
                        "id": "n1",
                        "kind": "task",
                        "objective": "run remote check",
                        "metadata": {"placement": {"mode": "node", "node_id": "node_worker"}},
                    }
                ],
            }
        )


def test_compile_rejects_invalid_placement() -> None:
    with pytest.raises(WorkGraphError, match="node placement requires node_id"):
        compile_work_graph(
            {
                "id": "g1",
                "objective": "remote",
                "nodes": [
                    {
                        "id": "n1",
                        "kind": "task",
                        "objective": "run remote check",
                        "placement": {"mode": "node"},
                    }
                ],
            }
        )
