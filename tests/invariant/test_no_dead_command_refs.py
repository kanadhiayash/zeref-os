"""SHR-Wave-8 regression: the active tree must not reference CLI commands that
do not exist. `shiroe grade` and `shiroe db` were never registered in
shiroe/cli/main.py but lingered as dependency-comment shorthand.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DEAD_COMMAND_PATTERNS = (
    re.compile(r"\bshiroe\s+grade\b"),
    re.compile(r"\bshiroe\s+db\b"),
)

# Files/dirs most likely to carry stale command references. Kept narrow and
# fast rather than walking the whole tree.
SCAN_TARGETS = (
    "pyproject.toml",
    "shiroe/adapters/providers/openai.json",
)

SCAN_DIRS = ("docs", "AGENTS.md")


def test_no_dead_command_refs_in_active_tree() -> None:
    hits: list[str] = []
    for rel in SCAN_TARGETS:
        path = ROOT / rel
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in DEAD_COMMAND_PATTERNS:
            if pattern.search(text):
                hits.append(f"{rel}: {pattern.pattern}")
    assert not hits, "\n".join(hits)


def test_registered_commands_do_not_include_grade_or_db() -> None:
    from shiroe.cli.main import registered_command_names

    names = registered_command_names()
    assert "grade" not in names
    assert "db" not in names
