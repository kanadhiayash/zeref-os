from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_single_memory_architecture():
    assert not (ROOT / "shiroe/guards").exists()
    assert not (ROOT / "shiroe/memory/indexer.py").exists()
    assert not (ROOT / "shiroe/memory/expand.py").exists()
    assert not (ROOT / "shiroe/memory/atom_store.py").exists()
    assert not (ROOT / "shiroe/memory/triples.py").exists()
    assert not (ROOT / "shiroe/memory/graph.py").exists()
