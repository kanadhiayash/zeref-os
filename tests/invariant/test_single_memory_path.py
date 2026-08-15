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


def test_memory_core_does_not_export_legacy_layout_api(tmp_path: Path):
    import shiroe.memory as memory
    import shiroe.memory.core as core

    for name in (
        "MEMORY_LAYERS",
        "MEMORY_DIRS",
        "MEMORY_FILES",
        "PROJECT_DIRS",
        "STATE_SCHEMA",
        "MemoryLayout",
    ):
        assert not hasattr(memory, name), name
        assert not hasattr(core, name), name

    memory_root = memory.MemoryRoot.from_path(tmp_path)
    assert memory_root.root == tmp_path.resolve()
    assert not hasattr(memory_root, "layout")
