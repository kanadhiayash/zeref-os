from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ACTIVE_ROOTS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "docs" / "GLOSSARY.md",
    ROOT / "docs" / "architecture",
    ROOT / "docs" / "wiki",
    ROOT / "shiroe",
    ROOT / "tests",
)

ALLOWLIST = {
    ROOT / "docs" / "architecture" / "REMOVALS.md",
    Path(__file__).resolve(),
}

FORBIDDEN = (
    re.compile(r"pattern-to-skill", re.I),
    re.compile(r"skill-importer", re.I),
    re.compile(r"fleet-activator", re.I),
    re.compile(r"caveman-handoff", re.I),
    re.compile(r"parent-sync", re.I),
    re.compile(r"skill-router", re.I),
    re.compile(r"budget-governor", re.I),
    re.compile(r"Team Packs"),
    re.compile(r"Mission seats", re.I),
    re.compile(r"\bBM25\b"),
    re.compile(r"benchmark score", re.I),
    re.compile(r"status:\s*contract", re.I),
    re.compile(r"status:\s*experimental", re.I),
    re.compile(r'"status"\s*:\s*"contract"', re.I),
    re.compile(r'"status"\s*:\s*"experimental"', re.I),
)


def _iter_active_files() -> list[Path]:
    files: list[Path] = []
    for root in ACTIVE_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files.append(path)
    return sorted(set(files))


def test_active_surface_has_no_dead_references():
    hits: list[str] = []
    for path in _iter_active_files():
        if path in ALLOWLIST:
            continue
        if path.suffix not in {".md", ".py", ".json", ".jsonl", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not hits, "\n".join(hits)


def test_removed_root_component_trees_are_absent():
    for rel in ("skills", "agents", "commands", "team-packs", "missions", "benchmarks"):
        assert not (ROOT / rel).exists(), rel


def test_removed_runtime_trees_and_registries_are_absent():
    for rel in (
        "shiroe/missions",
        "shiroe/teams",
        "shiroe/runtime",
        "shiroe/loops",
        "shiroe/benchmark",
        "shiroe/lineage",
    ):
        assert not (ROOT / rel).exists(), rel
    assert not (ROOT / "shiroe-registry.json").exists()
