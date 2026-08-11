from shiroe.policy.approval_service import ApprovalService
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


def _seed_graph_with_approval(root):
    graph = compile_work_graph(
        {
            "id": "g-approval",
            "objective": "publish",
            "nodes": [
                {
                    "id": "approval",
                    "kind": "approval",
                    "objective": "Approve publish",
                    "approval_required": True,
                    "metadata": {"scope": {"tag": "v1"}},
                },
                {
                    "id": "after",
                    "kind": "task",
                    "objective": "Publish",
                    "requires": ["test.publish"],
                },
            ],
            "edges": [{"from": "approval", "to": "after"}],
        }
    )
    WorkStore(root).create(graph)
    request = ApprovalService(root).request(
        approval_type="strategic",
        requested_action="publish v1",
        scope={"tag": "v1"},
        reason="graph approval node",
        risk="high",
        graph_id=graph.id,
        node_id="approval",
    )
    return graph.id, request.id


def test_downstream_node_waits_for_approved_current_scope(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    store = WorkStore(tmp_path)
    assert store.ready_node_ids(graph_id) == ("approval",)
    ApprovalService(tmp_path).decide_human(
        approval_id,
        decision="approved",
        actor="human",
        reason="approved",
    )
    store.refresh_readiness(graph_id)
    assert "after" in store.ready_node_ids(graph_id)


def test_stale_approval_reblocks_downstream_node(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    service = ApprovalService(tmp_path)
    service.decide_human(approval_id, decision="approved", actor="human", reason="approved")
    service.assert_current(approval_id, current_scope={"tag": "v2"})
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert "after" not in WorkStore(tmp_path).ready_node_ids(graph_id)
