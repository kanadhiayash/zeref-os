import pytest

from shiroe.work.schema import NodeKind, RetryPolicy, WorkGraph, WorkNode


def test_retry_policy_rejects_unbounded_attempts():
    with pytest.raises(ValueError, match="max_attempts"):
        RetryPolicy(max_attempts=0)


def test_work_node_rejects_unknown_kind():
    with pytest.raises(ValueError):
        WorkNode(id="n1", graph_id="g1", kind="worker", objective="x")


def test_work_node_defaults_are_bounded():
    node = WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="x")
    assert node.retry.max_attempts == 1
    assert node.requires == ()


def test_work_graph_rejects_empty_objective():
    node = WorkNode(id="n1", graph_id="g1", kind=NodeKind.task, objective="x")
    with pytest.raises(ValueError, match="objective"):
        WorkGraph(id="g1", objective="", nodes=(node,))
