import pytest

from shiroe.work.schema import NodeKind, WorkGraph, WorkNode
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore


def _graph():
    return WorkGraph(
        id="g1",
        objective="ship",
        nodes=(WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="inspect"),),
    )


def test_create_then_get_round_trips(tmp_path):
    store = WorkStore(tmp_path)
    store.create(_graph())
    assert store.get("g1").objective == "ship"


def test_record_output_round_trips_deterministically(tmp_path):
    store = WorkStore(tmp_path)
    store.create(_graph())
    version = store.node_state_version("n1")
    store.record_output("n1", {"b": 2, "a": 1}, expected_version=version)
    assert store.node_output("n1") == {"a": 1, "b": 2}


def test_node_transition_is_compare_and_swap(tmp_path):
    store = WorkStore(tmp_path)
    store.create(_graph())
    version = store.node_state_version("n1")
    store.set_node_status("n1", "running", expected_version=version)
    with pytest.raises(ConcurrentWorkUpdate):
        store.set_node_status("n1", "completed", expected_version=version)
