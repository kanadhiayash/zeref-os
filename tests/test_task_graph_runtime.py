"""SHR-105..108, 110: task-graph runtime parallel/sequential/loop/join/resume."""

from __future__ import annotations

import threading
import time

import pytest

from shiroe.graph import (
    LoopExceeded,
    compile_task_graph,
    run_task_graph,
)


def _make_executor(record: list, lock: threading.Lock):
    def _exec(node):
        with lock:
            record.append(("start", node["id"], time.monotonic()))
        time.sleep(0.02)
        with lock:
            record.append(("end", node["id"], time.monotonic()))
        return node["id"]
    return _exec


def test_parallel_ready_nodes_overlap() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [],
    })
    record: list = []
    lock = threading.Lock()
    run_task_graph(compiled, _make_executor(record, lock), max_workers=2)
    starts = {ev[1]: ev[2] for ev in record if ev[0] == "start"}
    ends = {ev[1]: ev[2] for ev in record if ev[0] == "end"}
    assert starts["b"] < ends["a"] or starts["a"] < ends["b"]


def test_sequential_edge_does_not_overlap() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b"}],
    })
    record: list = []
    lock = threading.Lock()
    run_task_graph(compiled, _make_executor(record, lock), max_workers=2)
    starts = {ev[1]: ev[2] for ev in record if ev[0] == "start"}
    ends = {ev[1]: ev[2] for ev in record if ev[0] == "end"}
    assert ends["a"] <= starts["b"]


def test_join_waits_for_every_predecessor() -> None:
    compiled = compile_task_graph({
        "nodes": [
            {"id": "a"}, {"id": "b"}, {"id": "j", "kind": "join"},
        ],
        "edges": [
            {"from": "a", "to": "j"},
            {"from": "b", "to": "j"},
        ],
    })
    record: list = []
    lock = threading.Lock()
    run_task_graph(compiled, _make_executor(record, lock), max_workers=3)
    ends = {ev[1]: ev[2] for ev in record if ev[0] == "end"}
    starts = {ev[1]: ev[2] for ev in record if ev[0] == "start"}
    assert starts["j"] >= ends["a"]
    assert starts["j"] >= ends["b"]


def test_loop_stops_at_bound() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "L", "kind": "loop"}],
        "edges": [],
    })
    with pytest.raises(LoopExceeded, match="loop"):
        run_task_graph(compiled, lambda n: n["id"], loop_bound=0)


def test_resume_skips_named_nodes() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}],
    })
    seen: list[str] = []
    def _exec(node):
        seen.append(node["id"])
        return node["id"]
    result = run_task_graph(compiled, _exec, resume_from={"a", "b"})
    assert seen == ["c"]
    assert result["skipped"] == ["a", "b"]
    assert result["completed"] == ["c"]


def test_diamond_topology_completes() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
        "edges": [
            {"from": "a", "to": "b"},
            {"from": "a", "to": "c"},
            {"from": "b", "to": "d"},
            {"from": "c", "to": "d"},
        ],
    })
    seen: list[str] = []
    lock = threading.Lock()
    def _exec(node):
        with lock:
            seen.append(node["id"])
        return node["id"]
    run_task_graph(compiled, _exec, max_workers=2)
    assert seen[0] == "a"
    assert seen[-1] == "d"
    assert set(seen[1:3]) == {"b", "c"}


def test_result_order_records_visit_order() -> None:
    compiled = compile_task_graph({
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b"}],
    })
    r = run_task_graph(compiled, lambda n: n["id"])
    assert r["order"] == ["a", "b"]
    assert r["results"] == {"a": "a", "b": "b"}
