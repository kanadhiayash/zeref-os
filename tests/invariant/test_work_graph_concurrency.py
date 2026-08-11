import pytest

from shiroe.work.schema import NodeKind, WorkGraph, WorkNode
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore


def test_stale_node_version_cannot_overwrite_terminal_status(tmp_path):
    store = WorkStore(tmp_path)
    graph = WorkGraph(
        id="g1",
        objective="ship",
        nodes=(WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="inspect"),),
    )
    store.create(graph)
    version = store.node_state_version("n1")
    store.set_node_status("n1", "completed", expected_version=version)

    with pytest.raises(ConcurrentWorkUpdate):
        store.set_node_status("n1", "failed", expected_version=version)
