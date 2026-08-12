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


def _approval_node_status(root, graph_id):
    return WorkStore(root).get_node("approval").status.value


def test_rejected_approval_fails_approval_node(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    ApprovalService(tmp_path).decide_human(
        approval_id, decision="rejected", actor="human", reason="not now"
    )
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert _approval_node_status(tmp_path, graph_id) == "failed"
    assert "after" not in WorkStore(tmp_path).ready_node_ids(graph_id)


def test_revise_approval_blocks_approval_node(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    ApprovalService(tmp_path).decide_human(
        approval_id, decision="revise", actor="human", reason="tighten scope"
    )
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert _approval_node_status(tmp_path, graph_id) == "blocked"
    assert "after" not in WorkStore(tmp_path).ready_node_ids(graph_id)


def test_deferred_approval_keeps_approval_node_pending(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    ApprovalService(tmp_path).decide_human(
        approval_id, decision="deferred", actor="human", reason="revisit next week"
    )
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert _approval_node_status(tmp_path, graph_id) == "pending"
    assert "after" not in WorkStore(tmp_path).ready_node_ids(graph_id)


def test_stale_approval_keeps_approval_node_pending(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    service = ApprovalService(tmp_path)
    service.decide_human(approval_id, decision="approved", actor="human", reason="approved")
    service.assert_current(approval_id, current_scope={"tag": "v2"})
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert _approval_node_status(tmp_path, graph_id) == "pending"


def test_rejected_approval_survives_second_refresh(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    ApprovalService(tmp_path).decide_human(
        approval_id, decision="rejected", actor="human", reason="no"
    )
    WorkStore(tmp_path).refresh_readiness(graph_id)
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert _approval_node_status(tmp_path, graph_id) == "failed"
