import pytest

from shiroe.work.schema import NodeKind, WorkGraph, WorkNode
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore


def test_stale_worker_cannot_write_output_after_status_transition(tmp_path):
    store = WorkStore(tmp_path)
    graph = WorkGraph(
        id="g-race",
        objective="race",
        nodes=(WorkNode(id="n1", graph_id="g-race", kind=NodeKind.task, objective="run"),),
    )
    store.create(graph)
    stale_version = store.node_state_version("n1")

    store.set_node_status("n1", "completed", expected_version=stale_version)

    with pytest.raises(ConcurrentWorkUpdate):
        store.record_output("n1", {"late": True}, expected_version=stale_version)

    assert store.node_output("n1") is None


def test_two_workers_cannot_claim_same_ready_node(tmp_path):
    store = WorkStore(tmp_path)
    graph = WorkGraph(
        id="g-claim",
        objective="claim",
        nodes=(WorkNode(id="n1", graph_id="g-claim", kind=NodeKind.task, objective="run"),),
    )
    store.create(graph)
    version = store.node_state_version("n1")

    store.set_node_status("n1", "running", expected_version=version)

    with pytest.raises(ConcurrentWorkUpdate):
        store.set_node_status("n1", "running", expected_version=version)
