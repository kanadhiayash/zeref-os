"""Task-graph compiler + runtime (Wave 6, PR26/PR27)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


NODE_KINDS = frozenset({"action", "gate", "join", "loop"})


class TaskGraphError(ValueError):
    """Raised when a task-graph spec violates its contract."""


def compile_task_graph(
    spec: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise TaskGraphError(f"spec must be a dict, got {type(spec).__name__}")
    nodes = spec.get("nodes")
    edges = spec.get("edges", [])
    if not isinstance(nodes, list) or not nodes:
        raise TaskGraphError("spec.nodes must be a non-empty list")
    if not isinstance(edges, list):
        raise TaskGraphError("spec.edges must be a list")

    known_ids: set[str] = set()
    normalized_nodes: list[dict[str, Any]] = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise TaskGraphError(f"node[{i}] must be a dict, got {type(node).__name__}")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise TaskGraphError(f"node[{i}] missing string id")
        if node_id in known_ids:
            raise TaskGraphError(f"duplicate node id: {node_id!r}")
        kind = node.get("kind", "action")
        if kind not in NODE_KINDS:
            raise TaskGraphError(
                f"node {node_id!r} has unknown kind {kind!r}; expected one of {sorted(NODE_KINDS)}"
            )
        irreversible = bool(node.get("irreversible", False))
        guarded = bool(node.get("guarded", False))
        if irreversible and not guarded:
            raise TaskGraphError(
                f"node {node_id!r} is irreversible but not guarded — refusing to compile"
            )
        artifacts = node.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise TaskGraphError(f"node {node_id!r} artifacts must be a list")
        if artifact_root is not None:
            for a in artifacts:
                if not isinstance(a, str):
                    raise TaskGraphError(
                        f"node {node_id!r} artifact must be str, got {type(a).__name__}"
                    )
                if not (Path(artifact_root) / a).is_file():
                    raise TaskGraphError(
                        f"node {node_id!r} artifact missing: {a}"
                    )
        known_ids.add(node_id)
        normalized_nodes.append({
            "id": node_id,
            "kind": kind,
            "irreversible": irreversible,
            "guarded": guarded,
            "artifacts": list(artifacts),
            "action": node.get("action"),
        })

    normalized_edges: list[dict[str, Any]] = []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise TaskGraphError(f"edge[{i}] must be a dict, got {type(edge).__name__}")
        src = edge.get("from")
        dst = edge.get("to")
        if src not in known_ids:
            raise TaskGraphError(f"edge[{i}] references unknown node: from={src!r}")
        if dst not in known_ids:
            raise TaskGraphError(f"edge[{i}] references unknown node: to={dst!r}")
        if src == dst:
            raise TaskGraphError(f"edge[{i}] is a self-loop on node {src!r}")
        normalized_edges.append({"from": src, "to": dst})

    return {
        "nodes": normalized_nodes,
        "edges": normalized_edges,
        "node_count": len(normalized_nodes),
        "edge_count": len(normalized_edges),
    }
