"""SHR-099..102, 111: derived-graph plane must not become a source of truth."""

from __future__ import annotations

import json
from pathlib import Path

from shiroe.memory.graph import (
    GRAPH_PATH,
    build_derived_graph,
    write_derived_graph,
)
from shiroe.memory.schemas import create_atom


def _atom(claim: str, entities: list[str], links: list[str] | None = None) -> dict:
    return create_atom(
        atom_type="fact",
        claim=claim,
        summary=claim[:60],
        source="note.md",
        entities=entities,
        links=links or [],
    )


def _root(tmp: Path) -> Path:
    (tmp / "memory" / "l1_atoms").mkdir(parents=True)
    (tmp / "memory" / "l1_atoms" / "facts.jsonl").write_text(
        "\n".join([
            json.dumps(_atom("A", ["shiroe"])),
            json.dumps(_atom("B", ["shiroe", "graph"], ["a1"])),
        ]) + "\n",
        encoding="utf-8",
    )
    return tmp


def test_derived_graph_is_never_canonical(tmp_path: Path) -> None:
    g = build_derived_graph(_root(tmp_path))
    assert g["canonical"] is False


def test_derived_graph_names_source_of_truth(tmp_path: Path) -> None:
    g = build_derived_graph(_root(tmp_path))
    assert "source_of_truth" in g
    assert "l1_atoms" in g["source_of_truth"] or "sqlite" in g["source_of_truth"]


def test_deleting_graph_cache_does_not_affect_canonical(tmp_path: Path) -> None:
    root = _root(tmp_path)
    write_derived_graph(root)
    cache = root / GRAPH_PATH
    assert cache.is_file()
    cache.unlink()
    canonical = root / "memory" / "l1_atoms" / "facts.jsonl"
    assert canonical.is_file()
    g = build_derived_graph(root)
    assert g["node_count"] > 0


def test_missing_atoms_returns_empty_graph_not_crash(tmp_path: Path) -> None:
    (tmp_path / "memory" / "l1_atoms").mkdir(parents=True)
    g = build_derived_graph(tmp_path)
    assert g["node_count"] == 0
    assert g["edge_count"] == 0
    assert g["canonical"] is False


def test_rebuild_reflects_current_state(tmp_path: Path) -> None:
    root = _root(tmp_path)
    initial = build_derived_graph(root)
    initial_nodes = initial["node_count"]
    with (root / "memory" / "l1_atoms" / "facts.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_atom("C", ["new-entity"])) + "\n")
    rebuilt = build_derived_graph(root)
    assert rebuilt["node_count"] > initial_nodes


def test_stale_cache_is_not_returned_by_build(tmp_path: Path) -> None:
    root = _root(tmp_path)
    write_derived_graph(root)
    cache = root / GRAPH_PATH
    cache.write_text(json.dumps({"node_count": 0, "edges": []}), encoding="utf-8")
    fresh = build_derived_graph(root)
    assert fresh["node_count"] > 0


def test_edges_ordered_deterministically(tmp_path: Path) -> None:
    g = build_derived_graph(_root(tmp_path))
    edges = g["edges"]
    keys = [(e["from"], e["kind"], e["to"]) for e in edges]
    assert keys == sorted(keys), "edges must be sorted deterministically"


def test_graph_write_creates_indexes_dir(tmp_path: Path) -> None:
    root = _root(tmp_path)
    result = write_derived_graph(root)
    assert Path(result["path"]).is_file()
    assert (root / GRAPH_PATH).is_file()
