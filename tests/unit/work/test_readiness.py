from shiroe.work.compiler import compile_work_graph
from shiroe.work.readiness import ready_node_ids


def test_ready_node_ids_starts_with_roots_only():
    graph = compile_work_graph(
        {
            "id": "g",
            "objective": "ship",
            "nodes": [
                {"id": "a", "kind": "task", "objective": "first"},
                {"id": "b", "kind": "task", "objective": "second"},
            ],
            "edges": [{"from": "a", "to": "b"}],
        }
    )
    assert ready_node_ids(graph, {"a": "pending", "b": "pending"}) == ("a",)


def test_ready_node_ids_unlocks_after_completed_or_skipped_predecessors():
    graph = compile_work_graph(
        {
            "id": "g",
            "objective": "ship",
            "nodes": [
                {"id": "a", "kind": "task", "objective": "first"},
                {"id": "b", "kind": "task", "objective": "second"},
                {"id": "c", "kind": "task", "objective": "third"},
            ],
            "edges": [{"from": "a", "to": "c"}, {"from": "b", "to": "c"}],
        }
    )
    assert ready_node_ids(graph, {"a": "completed", "b": "skipped", "c": "pending"}) == ("c",)


def test_approval_nodes_are_not_ready_until_phase_three_approval_records_exist():
    graph = compile_work_graph(
        {
            "id": "g",
            "objective": "ship",
            "nodes": [
                {
                    "id": "approve",
                    "kind": "approval",
                    "objective": "approve",
                    "approval_required": True,
                }
            ],
        }
    )
    assert ready_node_ids(graph, {"approve": "pending"}) == ()
