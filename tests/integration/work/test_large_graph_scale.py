"""H5.1: Work Graph scale invariants.

Pins the four scale cases the hardening plan calls out:
  - 1,000-node linear chain
  - 1,000-node wide DAG (one root -> 999 leaves)
  - 1,000-deep dependency chain (recursion-limit sentinel)
  - explicit cycle rejection

The 1,000-deep case is why _reject_cycles was converted from recursive
to iterative in shiroe/work/compiler.py; regressing that change would
crash this test with RecursionError, not silently.
"""

from __future__ import annotations

import pytest

from shiroe.work.compiler import WorkGraphError, compile_work_graph
from shiroe.work.store import WorkStore


N = 1_000


def _node(node_id: str) -> dict:
    return {"id": node_id, "kind": "task", "objective": node_id}


def test_linear_chain_of_one_thousand_nodes_compiles(tmp_path):
    nodes = [_node(f"n{i}") for i in range(N)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(N - 1)]
    graph = compile_work_graph({"id": "g-linear", "objective": "linear",
                                 "nodes": nodes, "edges": edges})
    assert len(graph.nodes) == N
    WorkStore(tmp_path).create(graph)
    ready = WorkStore(tmp_path).ready_node_ids(graph.id)
    assert ready == ("n0",)


def test_wide_dag_of_one_thousand_nodes_compiles(tmp_path):
    nodes = [_node("root")] + [_node(f"leaf{i}") for i in range(N - 1)]
    edges = [{"from": "root", "to": f"leaf{i}"} for i in range(N - 1)]
    graph = compile_work_graph({"id": "g-wide", "objective": "wide",
                                 "nodes": nodes, "edges": edges})
    assert len(graph.nodes) == N
    WorkStore(tmp_path).create(graph)
    ready = WorkStore(tmp_path).ready_node_ids(graph.id)
    assert ready == ("root",)


def test_deep_chain_does_not_hit_recursion_limit():
    nodes = [_node(f"d{i}") for i in range(N)]
    edges = [{"from": f"d{i}", "to": f"d{i+1}"} for i in range(N - 1)]
    graph = compile_work_graph({"id": "g-deep", "objective": "deep",
                                 "nodes": nodes, "edges": edges})
    assert len(graph.nodes) == N


def test_cycle_is_rejected_with_explicit_message():
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [
        {"from": "a", "to": "b"},
        {"from": "b", "to": "c"},
        {"from": "c", "to": "a"},
    ]
    with pytest.raises(WorkGraphError, match="cycle"):
        compile_work_graph({"id": "g-cycle", "objective": "cycle",
                            "nodes": nodes, "edges": edges})


def test_deep_cycle_is_rejected_iteratively():
    nodes = [_node(f"c{i}") for i in range(N)]
    edges = [{"from": f"c{i}", "to": f"c{i+1}"} for i in range(N - 1)]
    edges.append({"from": f"c{N-1}", "to": "c0"})
    with pytest.raises(WorkGraphError, match="cycle"):
        compile_work_graph({"id": "g-deep-cycle", "objective": "deep-cycle",
                            "nodes": nodes, "edges": edges})
