import pytest

from shiroe.work.compiler import WorkGraphError, compile_work_graph
from shiroe.work.schema import NodeKind


@pytest.mark.parametrize(
    ("spec", "fragment"),
    [
        ({"id": "g", "objective": "x", "nodes": []}, "nodes"),
        (
            {
                "id": "g",
                "objective": "x",
                "nodes": [
                    {"id": "a", "kind": "task", "objective": "x"},
                    {"id": "a", "kind": "task", "objective": "y"},
                ],
            },
            "duplicate",
        ),
        (
            {
                "id": "g",
                "objective": "x",
                "nodes": [{"id": "a", "kind": "task", "objective": "x"}],
                "edges": [{"from": "a", "to": "missing"}],
            },
            "unknown",
        ),
        (
            {
                "id": "g",
                "objective": "x",
                "nodes": [{"id": "a", "kind": "ritual", "objective": "x"}],
            },
            "unknown",
        ),
        (
            {
                "id": "g",
                "objective": "x",
                "nodes": [{"id": "a", "kind": "task", "objective": "x"}],
                "edges": [{"from": "a", "to": "a"}],
            },
            "self-edge",
        ),
    ],
)
def test_compile_rejects_invalid_graph(spec, fragment):
    with pytest.raises(WorkGraphError, match=fragment):
        compile_work_graph(spec)


def test_compile_rejects_cycles():
    with pytest.raises(WorkGraphError, match="cycle"):
        compile_work_graph(
            {
                "id": "g",
                "objective": "x",
                "nodes": [
                    {"id": "a", "kind": "task", "objective": "x"},
                    {"id": "b", "kind": "task", "objective": "y"},
                ],
                "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
            }
        )


def test_compile_requires_approval_nodes_to_require_approval():
    with pytest.raises(WorkGraphError, match="approval_required"):
        compile_work_graph(
            {
                "id": "g",
                "objective": "x",
                "nodes": [{"id": "a", "kind": "approval", "objective": "approve"}],
            }
        )


def test_compile_normalizes_nodes_and_edges():
    graph = compile_work_graph(
        {
            "id": "g",
            "objective": "x",
            "nodes": [
                {"id": "b", "kind": "task", "objective": "second"},
                {"id": "a", "kind": "task", "objective": "first"},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
    )
    assert [node.id for node in graph.nodes] == ["a", "b"]
    assert graph.edges[0].src_id == "a"
    assert graph.nodes[0].kind is NodeKind.task
