"""Graph exports (Wave 6, PR29)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from shiroe.graph.knowledge import KnowledgeGraph


PRIVATE_KINDS = frozenset({"sensitive", "secret", "do_not_store"})


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def export_projection(
    kg: KnowledgeGraph,
    *,
    include_private: bool = False,
    adapters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    adapters = adapters or {}
    kept_ids: set[str] = set()
    nodes_out: list[dict[str, Any]] = []
    for node in sorted(kg._nodes.values(), key=lambda n: n.id):
        priv = node.attrs.get("privacy") if isinstance(node.attrs, dict) else None
        if not include_private and priv in PRIVATE_KINDS:
            continue
        kept_ids.add(node.id)
        nodes_out.append({"id": node.id, "kind": node.kind, "attrs": dict(node.attrs or {})})

    edges_out: list[dict[str, Any]] = []
    for e in kg.edges():
        if e.subject not in kept_ids or e.object not in kept_ids:
            continue
        edges_out.append({
            "subject": e.subject,
            "predicate": e.predicate,
            "object": e.object,
            "provenance": e.provenance,
        })
    edges_out.sort(key=lambda e: (e["subject"], e["predicate"], e["object"], e["provenance"]))

    payload = {"nodes": nodes_out, "edges": edges_out}
    payload["digest"] = _digest(payload)

    views: dict[str, Any] = {}
    for name, adapter in adapters.items():
        renderer = getattr(adapter, "render", None)
        if renderer is None:
            continue
        views[name] = renderer(edges_out)
    if views:
        payload["views"] = views
    return payload


def write_projection(kg: KnowledgeGraph, path: Path, **kwargs) -> Path:
    payload = export_projection(kg, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
