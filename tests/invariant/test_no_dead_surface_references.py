from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ROOT_OPERATIONAL_FILES = (
    "AGENTS.md",
    "SOUL.md",
    "SKILL.md",
    "CLAUDE.md",
    "CODEX.md",
    "GEMINI.md",
    "LLAMA.md",
    "README.md",
    "QUICKSTART.md",
    "INSTALL.md",
    "GITHUB_OS.md",
    "PRIVACY.md",
    "REDACT.md",
    "SHARING_POLICY.md",
    ".aider.conf.yml.example",
    ".windsurfrules",
)

ACTIVE_DOC_FILES = (
    "docs/DOCTOR.md",
    "docs/GETTING_STARTED.md",
    "docs/GLOSSARY.md",
    "docs/HARNESS_MATRIX.md",
    "docs/MEMORY_WRITES.md",
    "docs/architecture/CORE_SCOPE.md",
    "docs/canon/SOURCE_AUTHORITY.md",
    "docs/wiki/Memory-Model.md",
    "docs/wiki/Stack.md",
    "memory/README.md",
    "references/harness-translation-map.md",
    "references/shared-anti-hallucination.md",
    "references/shiroe-qa-gate.md",
    "references/shiroe-safety-principles.md",
)

ACTIVE_DIRS = (
    ".claude-plugin",
    ".cursor",
    ".github",
    "config",
    "shiroe",
)

RELEASE_GATE_SCRIPTS = (
    "scripts/release_ready.py",
    "scripts/shiroe-validate.py",
    "scripts/check-version-consistency.py",
    "scripts/check-active-identity.py",
)

TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".txt", ".yml", ".yaml", ".example"}


def _phrase(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN = tuple(
    re.compile(pattern, flags)
    for pattern, flags in (
        (_phrase("shiroe", "-runtime"), re.I),
        (_phrase("privacy", "-guardian"), re.I),
        (_phrase("project", "-setup"), re.I),
        (_phrase("wiki", "-maintenance"), re.I),
        (_phrase("evidence", "-grader"), re.I),
        (_phrase("pattern", "-observer"), re.I),
        (_phrase("skill", "-router"), re.I),
        (_phrase("budget", "-governor"), re.I),
        (_phrase("pattern", "-to-", "skill"), re.I),
        (_phrase("skill", "-importer"), re.I),
        (_phrase("fleet", "-activator"), re.I),
        (_phrase("caveman", "-handoff"), re.I),
        (_phrase("parent", "-sync"), re.I),
        (_phrase("sync", "-coordinator"), re.I),
        (_phrase(r"\bTeam ", r"Packs?\b"), 0),
        (_phrase(r"\bteam ", r"packs?\b"), re.I),
        (_phrase(r"\bMission ", r"Packs?\b"), 0),
        (_phrase(r"\bMission ", r"Seats?\b"), re.I),
        (_phrase("PATTERNS", r"\.jsonl"), 0),
        (_phrase("skills", r"/drafts"), 0),
        (_phrase("memory", r"/hot\.md"), 0),
        (_phrase("memory", r"/index\.md"), 0),
        (_phrase("/", "shiroe", ":start"), 0),
        (_phrase("/", "shiroe", ":done"), 0),
        (_phrase("/", "shiroe", ":stop"), 0),
        (_phrase("/", "shiroe", ":team"), 0),
        (_phrase("/", "shiroe", ":sync-parent"), 0),
        (_phrase("/", "shiroe", ":reset-permissions"), 0),
        (_phrase("/", "shiroe", ":review-skill"), 0),
        (_phrase("active", "_agents"), 0),
        (_phrase("active", "_skills"), 0),
        (r"status:\s*contract", re.I),
        (r"status:\s*experimental", re.I),
        (r'"status"\s*:\s*"contract"', re.I),
        (r'"status"\s*:\s*"experimental"', re.I),
    )
)

NVIDIA_RUNTIME_PATTERNS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        _phrase("nvidia", r"\s+adapter"),
        _phrase("cuda", r"\s+adapter"),
        _phrase("tensorrt", r"\s+adapter"),
        _phrase("NIM", r"\s+(?:provider|adapter)"),
        _phrase("NeMo", r"\s+adapter"),
    )
)


def test_active_surface_has_no_dead_references() -> None:
    hits: list[str] = []
    for path in _iter_active_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not hits, "\n".join(hits)


def test_active_runtime_has_no_nvidia_specific_dependency() -> None:
    hits: list[str] = []
    for path in _iter_nvidia_guard_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in NVIDIA_RUNTIME_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
    assert not hits, "\n".join(hits)


def test_removed_root_component_trees_are_absent() -> None:
    for rel in ("skills", "agents", "commands", "team" + "-packs", "missions", "benchmarks"):
        assert not (ROOT / rel).exists(), rel


def test_removed_runtime_trees_and_registries_are_absent() -> None:
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


def test_b1_orphan_execution_and_prompt_surfaces_are_absent() -> None:
    for rel in (
        "shiroe/prompt",
        "shiroe/execution/criticality.py",
        "shiroe/execution/reasoning.py",
        "references/target-model-profiles",
    ):
        assert not (ROOT / rel).exists(), rel


def test_b3_contradiction_guard_doc_is_absent() -> None:
    assert not (ROOT / "docs" / "CONTRADICTIONGUARD.md").exists()


def _iter_active_files() -> list[Path]:
    files: set[Path] = set()
    for rel in (*ROOT_OPERATIONAL_FILES, *ACTIVE_DOC_FILES, *RELEASE_GATE_SCRIPTS):
        path = ROOT / rel
        if path.is_file() and _is_text(path):
            files.add(path)
    for rel in ACTIVE_DIRS:
        root = ROOT / rel
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and _is_text(path) and "__pycache__" not in path.parts:
                files.add(path)
    return sorted(files)


def _iter_nvidia_guard_files() -> list[Path]:
    files: set[Path] = set()
    for rel in (*ROOT_OPERATIONAL_FILES, "config/PROJECT.md"):
        path = ROOT / rel
        if path.is_file() and _is_text(path):
            files.add(path)
    for root_rel in ("shiroe", "config"):
        for path in (ROOT / root_rel).rglob("*"):
            if path.is_file() and _is_text(path) and "__pycache__" not in path.parts:
                files.add(path)
    return sorted(files)


def _is_text(path: Path) -> bool:
    return path.suffix in TEXT_SUFFIXES or path.name in {".windsurfrules"}
