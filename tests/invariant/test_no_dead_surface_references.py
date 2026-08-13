from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _root_markdown_files() -> tuple[Path, ...]:
    """Root-level *.md files (harness shims, contributor docs, guides)."""
    return tuple(sorted(p for p in ROOT.glob("*.md") if p.is_file()))


ACTIVE_ROOTS: tuple[Path, ...] = (
    *_root_markdown_files(),
    ROOT / ".aider.conf.yml.example",
    ROOT / ".claude-plugin",
    ROOT / ".cursor",
    ROOT / ".windsurfrules",
    ROOT / "_shared",
    ROOT / "config",
    ROOT / "docs" / "GLOSSARY.md",
    ROOT / "docs" / "architecture",
    ROOT / "docs" / "wiki",
    ROOT / "references",
    ROOT / "shiroe",
    ROOT / "tests",
)

ALLOWLIST = {
    # Retirement register: intentionally names removed surfaces.
    ROOT / "docs" / "architecture" / "REMOVALS.md",
    # Identity-only compatibility register (post-Phase-08 shape).
    ROOT / "docs" / "DEPRECATIONS.md",
    # Migration guide: legitimate references to pre-rebrand names.
    ROOT / "MIGRATION.md",
    # Release notes: append-only historical claims.
    ROOT / "CHANGELOG.md",
    # Canon docs (pre-vNext architecture snapshots kept for parity with
    # the parent project; not our active surface to rewrite unilaterally).
    ROOT / "references" / "v4x-canon" / "SHIROE_OS.md",
    ROOT / "references" / "v4x-canon" / "DECISION_LOG.md",
    ROOT / "references" / "v4x-canon" / "MODEL_DEBATE.md",
    # Target-model profiles: describe cross-harness handoff features from
    # the shared harness catalog, not vNext product surfaces.
    ROOT / "references" / "target-model-profiles" / "README.md",
    ROOT / "references" / "target-model-profiles" / "claude-opus-4-8.md",
    ROOT / "references" / "target-model-profiles" / "gpt-5-5-instant.md",
    # Retired-feature reference doc: documents a superseded sub-system
    # (parent sync). Retained as historical reference; not scaffolded.
    ROOT / "config" / "PARENT_SYNC.md",
    # Shared cross-agent enforcement rules; retired-agent names remain as
    # per-agent scoping tokens for a rule set that predates vNext.
    ROOT / "_shared" / "rules.md",
    # This scanner file itself: contains the pattern strings by definition.
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
    # Retired product surfaces: proper-noun / hyphenated forms only so English
    # prose like "mission-critical" or "seat belt" cannot false-hit.
    re.compile(r"\bTeam Packs?\b"),
    re.compile(r"\bMission Packs?\b"),
    re.compile(r"\bMission Seats?\b", re.I),
    re.compile(r"\bBM25\b"),
    re.compile(r"benchmark score", re.I),
    re.compile(r"status:\s*contract", re.I),
    re.compile(r"status:\s*experimental", re.I),
    re.compile(r'"status"\s*:\s*"contract"', re.I),
    re.compile(r'"status"\s*:\s*"experimental"', re.I),
    # Retired runtime identities / view names (H0 residue).
    re.compile(r"memory-keeper"),
    re.compile(r"\bactive-team\b"),
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
