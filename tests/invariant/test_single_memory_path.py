from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_single_memory_architecture():
    removed = (
        ("shiroe", "guards"),
        ("shiroe", "memory", "indexer.py"),
        ("shiroe", "memory", "expand.py"),
        ("shiroe", "memory", "atom_store.py"),
        ("shiroe", "memory", "triples.py"),
        ("shiroe", "memory", "graph.py"),
    )
    for parts in removed:
        assert not ROOT.joinpath(*parts).exists()
