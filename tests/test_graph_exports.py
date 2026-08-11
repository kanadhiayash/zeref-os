"""SHR-119..124: graph exports are privacy-filtered, adapter-absent-safe,
and reproducibly regenerated."""

from __future__ import annotations

import json
from pathlib import Path

from shiroe.graph import (
    Edge,
    KnowledgeGraph,
    Node,
    export_projection,
    write_projection,
)


def _kg_with_private() -> KnowledgeGraph:
    kg = KnowledgeGraph()
    kg.add_node(Node("alice", "person", {"privacy": "public"}))
    kg.add_node(Node("bob", "person", {"privacy": "sensitive"}))
    kg.add_node(Node("shiroe", "project"))
    kg.add_edge(Edge("shiroe", "authored_by", "alice", "atom:a1"))
    kg.add_edge(Edge("shiroe", "authored_by", "bob", "atom:a2"))
    return kg


def test_private_nodes_are_filtered_out_by_default() -> None:
    p = export_projection(_kg_with_private())
    ids = {n["id"] for n in p["nodes"]}
    assert "bob" not in ids
    assert not any(e["object"] == "bob" for e in p["edges"])
    assert any(e["object"] == "alice" for e in p["edges"])


def test_private_nodes_included_when_flag_set() -> None:
    p = export_projection(_kg_with_private(), include_private=True)
    ids = {n["id"] for n in p["nodes"]}
    assert "bob" in ids


def test_export_is_deterministic() -> None:
    p1 = export_projection(_kg_with_private())
    p2 = export_projection(_kg_with_private())
    assert p1 == p2
    assert p1["digest"] == p2["digest"]


def test_absent_adapter_does_not_break_export() -> None:
    class NoRender:
        pass
    p = export_projection(_kg_with_private(), adapters={"missing": NoRender()})
    assert "views" not in p


def test_present_adapter_render_lands_in_views() -> None:
    class Adapter:
        def render(self, edges):
            return {"edge_count": len(edges), "predicates": sorted({e["predicate"] for e in edges})}
    p = export_projection(_kg_with_private(), adapters={"summary": Adapter()})
    assert p["views"]["summary"]["edge_count"] == 1
    assert p["views"]["summary"]["predicates"] == ["authored_by"]


def test_rebuild_reproduces_projection_from_disk(tmp_path: Path) -> None:
    kg = _kg_with_private()
    written = write_projection(kg, tmp_path / "graph.json")
    on_disk = json.loads(written.read_text(encoding="utf-8"))
    fresh = export_projection(_kg_with_private())
    assert on_disk["nodes"] == fresh["nodes"]
    assert on_disk["edges"] == fresh["edges"]
    assert on_disk["digest"] == fresh["digest"]


def test_edges_are_sorted_deterministically() -> None:
    kg = KnowledgeGraph()
    kg.add_node(Node("p1", "project"))
    kg.add_node(Node("p2", "project"))
    kg.add_node(Node("p3", "project"))
    kg.add_edge(Edge("p3", "depends_on", "p1", "atom:c"))
    kg.add_edge(Edge("p1", "depends_on", "p2", "atom:a"))
    kg.add_edge(Edge("p2", "depends_on", "p3", "atom:b"))
    p = export_projection(kg)
    keys = [(e["subject"], e["predicate"], e["object"]) for e in p["edges"]]
    assert keys == sorted(keys)


def test_write_projection_creates_parent_directories(tmp_path: Path) -> None:
    kg = _kg_with_private()
    target = tmp_path / "nested" / "dirs" / "graph.json"
    assert not target.parent.is_dir()
    write_projection(kg, target)
    assert target.is_file()
