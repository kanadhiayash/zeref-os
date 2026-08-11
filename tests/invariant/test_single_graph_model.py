from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_no_generic_knowledge_graph_runtime():
    assert not (ROOT / "shiroe/graph/knowledge.py").exists()
    assert not (ROOT / "shiroe/graph/exports.py").exists()


def test_work_graph_runtime_exists():
    assert (ROOT / "shiroe/work/schema.py").is_file()
    assert (ROOT / "shiroe/work/compiler.py").is_file()
    assert (ROOT / "shiroe/work/store.py").is_file()
