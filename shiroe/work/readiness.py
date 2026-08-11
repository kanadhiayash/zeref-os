"""Readiness calculation for canonical Work Graphs."""

from __future__ import annotations

from collections.abc import Mapping

from shiroe.work.schema import NodeKind, NodeStatus, WorkGraph

_READY_PREDECESSORS = {NodeStatus.completed.value, NodeStatus.skipped.value}


def ready_node_ids(graph: WorkGraph, statuses: Mapping[str, str]) -> tuple[str, ...]:
    predecessors: dict[str, set[str]] = {node.id: set() for node in graph.nodes}
    for edge in graph.edges:
        predecessors[edge.dst_id].add(edge.src_id)

    ready: list[str] = []
    nodes_by_id = {node.id: node for node in graph.nodes}
    for node_id in sorted(nodes_by_id):
        node = nodes_by_id[node_id]
        if statuses.get(node_id, NodeStatus.pending.value) != NodeStatus.pending.value:
            continue
        if node.kind is NodeKind.approval:
            continue
        if all(statuses.get(pred) in _READY_PREDECESSORS for pred in predecessors[node_id]):
            ready.append(node_id)
    return tuple(ready)
