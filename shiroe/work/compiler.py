"""Compiler for canonical Work Graph specs."""

from __future__ import annotations

from typing import Any

from shiroe.work.schema import NodeKind, Placement, RetryPolicy, WorkEdge, WorkGraph, WorkNode


class WorkGraphError(ValueError):
    """Raised when a Work Graph spec violates the canonical graph contract."""


def _expect_mapping(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise WorkGraphError(f"spec must be a dict, got {type(spec).__name__}")
    return spec


def _node(raw: Any, graph_id: str) -> WorkNode:
    if not isinstance(raw, dict):
        raise WorkGraphError(f"node must be a dict, got {type(raw).__name__}")
    try:
        metadata = dict(raw.get("metadata", {}))
        if "placement" in metadata:
            raise ValueError("node placement must use top-level placement, not metadata")
        retry_raw = raw.get("retry", {})
        retry = retry_raw if isinstance(retry_raw, RetryPolicy) else RetryPolicy(**retry_raw)
        placement_raw = raw.get("placement", {})
        placement = placement_raw if isinstance(placement_raw, Placement) else Placement(**placement_raw)
        node = WorkNode(
            id=raw.get("id", ""),
            graph_id=graph_id,
            kind=raw.get("kind", NodeKind.task),
            objective=raw.get("objective", ""),
            requires=tuple(raw.get("requires", ())),
            risk=raw.get("risk", "low"),
            approval_required=bool(raw.get("approval_required", False)),
            independent_review=bool(raw.get("independent_review", False)),
            evidence_required=bool(raw.get("evidence_required", False)),
            expected_outputs=tuple(raw.get("expected_outputs", ())),
            retry=retry,
            placement=placement,
            metadata=metadata,
        )
    except (TypeError, ValueError) as exc:
        raise WorkGraphError(str(exc)) from exc
    if node.kind is NodeKind.approval and not node.approval_required:
        raise WorkGraphError("approval nodes must set approval_required=True")
    return node


def _edge(raw: Any, graph_id: str) -> WorkEdge:
    if not isinstance(raw, dict):
        raise WorkGraphError(f"edge must be a dict, got {type(raw).__name__}")
    src = raw.get("from", raw.get("src_id", ""))
    dst = raw.get("to", raw.get("dst_id", ""))
    try:
        return WorkEdge(graph_id=graph_id, src_id=src, dst_id=dst)
    except ValueError as exc:
        raise WorkGraphError(str(exc)) from exc


def _reject_cycles(node_ids: set[str], edges: tuple[WorkEdge, ...]) -> None:
    """Iterative DFS cycle detector.

    H5.1: the previous recursive implementation exhausted Python's
    default recursion limit on a 1000-deep linear graph. This iterative
    variant preserves the same external contract (raises WorkGraphError
    with message "graph contains a cycle" iff a directed cycle exists)
    but uses an explicit stack so it scales to arbitrary depth.
    """
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        outgoing[edge.src_id].append(edge.dst_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    for root in sorted(node_ids):
        if root in visited:
            continue
        stack: list[tuple[str, "iter[str]"]] = [(root, iter(outgoing[root]))]
        visiting.add(root)
        while stack:
            node_id, children = stack[-1]
            try:
                child = next(children)
            except StopIteration:
                visiting.discard(node_id)
                visited.add(node_id)
                stack.pop()
                continue
            if child in visiting:
                raise WorkGraphError("graph contains a cycle")
            if child in visited:
                continue
            visiting.add(child)
            stack.append((child, iter(outgoing[child])))


def compile_work_graph(spec: dict[str, Any]) -> WorkGraph:
    raw = _expect_mapping(spec)
    graph_id = raw.get("id", "")
    if not isinstance(raw.get("nodes"), list) or not raw["nodes"]:
        raise WorkGraphError("spec.nodes must be a non-empty list")

    nodes_by_id: dict[str, WorkNode] = {}
    for item in raw["nodes"]:
        node = _node(item, graph_id)
        if node.id in nodes_by_id:
            raise WorkGraphError(f"duplicate node id: {node.id!r}")
        nodes_by_id[node.id] = node

    edges = tuple(sorted((_edge(e, graph_id) for e in raw.get("edges", [])), key=lambda e: (e.src_id, e.dst_id)))
    for edge in edges:
        if edge.src_id not in nodes_by_id:
            raise WorkGraphError(f"edge references unknown node: from={edge.src_id!r}")
        if edge.dst_id not in nodes_by_id:
            raise WorkGraphError(f"edge references unknown node: to={edge.dst_id!r}")
    _reject_cycles(set(nodes_by_id), edges)

    try:
        return WorkGraph(
            id=graph_id,
            objective=raw.get("objective", ""),
            nodes=tuple(nodes_by_id[node_id] for node_id in sorted(nodes_by_id)),
            edges=edges,
            constraints=tuple(raw.get("constraints", ())),
            success_criteria=tuple(raw.get("success_criteria", ())),
            status=raw.get("status", "draft"),
            version=int(raw.get("version", 1)),
            metadata=dict(raw.get("metadata", {})),
        )
    except (TypeError, ValueError) as exc:
        raise WorkGraphError(str(exc)) from exc
