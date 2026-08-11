"""Task-graph runtime (Wave 6, PR27)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

from shiroe.graph.task_graph import TaskGraphError


class LoopExceeded(TaskGraphError):
    """Raised when a loop node exceeds its bound."""


def _predecessors(compiled: dict) -> dict[str, list[str]]:
    preds: dict[str, list[str]] = {n["id"]: [] for n in compiled["nodes"]}
    for e in compiled["edges"]:
        preds[e["to"]].append(e["from"])
    return preds


def run_task_graph(
    compiled: dict,
    executor: Callable[[dict], object],
    *,
    resume_from: Iterable[str] | None = None,
    loop_bound: int = 100,
    max_workers: int = 4,
) -> dict:
    nodes_by_id = {n["id"]: n for n in compiled["nodes"]}
    preds = _predecessors(compiled)

    skipped = set(resume_from or ())
    completed: set[str] = set(skipped)
    results: dict[str, object] = {}
    loop_counts: dict[str, int] = {}
    order: list[str] = []

    def _ready() -> list[str]:
        return [
            nid for nid in nodes_by_id
            if nid not in completed
            and all(p in completed for p in preds[nid])
        ]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while len(completed) < len(nodes_by_id):
            batch = _ready()
            if not batch:
                pending = [n for n in nodes_by_id if n not in completed]
                raise TaskGraphError(
                    f"deadlock: no ready nodes among pending {pending}"
                )
            for nid in batch:
                if nodes_by_id[nid]["kind"] == "loop":
                    loop_counts[nid] = loop_counts.get(nid, 0) + 1
                    if loop_counts[nid] > loop_bound:
                        raise LoopExceeded(
                            f"loop node {nid!r} exceeded bound {loop_bound}"
                        )
            futures = {pool.submit(executor, nodes_by_id[nid]): nid for nid in batch}
            for fut in list(futures):
                nid = futures[fut]
                results[nid] = fut.result()
                completed.add(nid)
                order.append(nid)

    return {
        "completed": sorted(completed - skipped),
        "skipped": sorted(skipped),
        "results": results,
        "order": order,
        "loop_counts": loop_counts,
    }
