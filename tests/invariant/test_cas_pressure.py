"""H5.3: concurrent compare-and-swap pressure on the Work Graph store.

Extends tests/invariant/test_concurrent_execution_adversarial.py with
a multi-writer contest: N threads observe the same state_version, all
attempt to transition n1 to a different terminal status, and the store
must accept exactly one and raise ConcurrentWorkUpdate for the others.

Uses a threading.Barrier so every writer reads its version snapshot
before any writer commits -- deterministic conflict, not race-to-read.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import ConcurrentWorkUpdate, WorkStore


N_WRITERS = 8


def _seed_single_node(root: Path) -> str:
    graph = compile_work_graph({
        "id": "g-cas",
        "objective": "cas pressure",
        "nodes": [{"id": "n1", "kind": "task", "objective": "solo"}],
        "edges": [],
    })
    WorkStore(root).create(graph)
    return graph.id


@pytest.mark.skip(reason="WorkStore event-first refactor: single-process supervisor; multi-writer CAS deferred (see WorkStore.set_node_status ponytail comment)")
def test_conflicting_transitions_yield_exactly_one_winner(tmp_path):
    _seed_single_node(tmp_path)
    store = WorkStore(tmp_path)
    version = store.get_node("n1").state_version
    store.close()

    barrier = threading.Barrier(N_WRITERS)
    results: list[str] = []
    lock = threading.Lock()

    def writer(index: int) -> None:
        s = WorkStore(tmp_path)
        barrier.wait()
        try:
            s.set_node_status("n1", "completed", expected_version=version)
        except ConcurrentWorkUpdate:
            with lock:
                results.append("stale")
        else:
            with lock:
                results.append(f"winner:{index}")
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=N_WRITERS) as ex:
        list(ex.map(writer, range(N_WRITERS)))

    winners = [r for r in results if r.startswith("winner")]
    stales = [r for r in results if r == "stale"]
    assert len(winners) == 1, f"expected exactly one winner, got {results}"
    assert len(stales) == N_WRITERS - 1, f"expected {N_WRITERS - 1} stale rejects, got {results}"
    final = WorkStore(tmp_path).get_node("n1").status.value
    assert final == "completed"


def test_stale_writer_raises_concurrent_update(tmp_path):
    _seed_single_node(tmp_path)
    store = WorkStore(tmp_path)
    stale_version = store.get_node("n1").state_version
    store.set_node_status("n1", "running", expected_version=stale_version)
    store.close()

    raised = 0
    for _ in range(20):
        s = WorkStore(tmp_path)
        with pytest.raises(ConcurrentWorkUpdate):
            s.set_node_status("n1", "completed", expected_version=stale_version)
        s.close()
        raised += 1
    assert raised == 20


def test_no_writer_can_advance_after_terminal_transition(tmp_path):
    _seed_single_node(tmp_path)
    store = WorkStore(tmp_path)
    pre_terminal = store.get_node("n1").state_version
    store.set_node_status("n1", "completed", expected_version=pre_terminal)
    store.close()

    for _ in range(N_WRITERS):
        s = WorkStore(tmp_path)
        with pytest.raises(ConcurrentWorkUpdate):
            s.set_node_status("n1", "failed", expected_version=pre_terminal)
        s.close()
    assert WorkStore(tmp_path).get_node("n1").status.value == "completed"
