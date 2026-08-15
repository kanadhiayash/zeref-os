from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DOCS = (
    ROOT / "README.md",
    ROOT / "QUICKSTART.md",
    ROOT / "INSTALL.md",
    ROOT / "docs" / "GETTING_STARTED.md",
    ROOT / "docs" / "HARNESS_MATRIX.md",
    ROOT / "docs" / "MEMORY_WRITES.md",
    ROOT / "docs" / "DOCTOR.md",
    ROOT / "docs" / "wiki" / "Memory-Model.md",
    ROOT / "memory" / "README.md",
    ROOT / "references" / "shiroe-qa-gate.md",
    ROOT / "references" / "shiroe-safety-principles.md",
    ROOT / "references" / "harness-translation-map.md",
    ROOT / "references" / "shared-anti-hallucination.md",
)

GROUPS = {
    "approve": {"list", "decide", "advise"},
    "capability": {"list", "show", "doctor", "invoke"},
    "memory": {"write", "recall", "list", "show", "supersede", "archive", "views"},
    "node": {"list", "discover", "register", "inspect", "probe", "trust", "untrust", "doctor", "worker-run"},
    "policy": {"show", "authorize"},
    "state": {"migrate", "verify", "export", "backup", "rollback", "replay"},
}


def test_documented_shiroe_commands_have_parser_help() -> None:
    checked: set[tuple[str, ...]] = set()
    for path in DOCS:
        for command in _shiroe_commands(path.read_text(encoding="utf-8")):
            help_args = _help_args(command)
            if help_args in checked:
                continue
            checked.add(help_args)
            result = subprocess.run(
                [sys.executable, "-m", "shiroe", *help_args],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            assert result.returncode == 0, f"{path.relative_to(ROOT)}: {' '.join(command)}\n{result.stderr}"

    assert checked


def _shiroe_commands(text: str) -> list[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        stripped = re.sub(r"\s+#.*$", "", stripped)
        if stripped.startswith("python3 -m shiroe "):
            commands.append(tuple(shlex.split(stripped)[3:]))
        elif stripped.startswith("shiroe "):
            commands.append(tuple(shlex.split(stripped)[1:]))
    return commands


def _help_args(command: tuple[str, ...]) -> tuple[str, ...]:
    if not command:
        return ("--help",)
    first = command[0]
    if first in {"--help", "-h", "--version"}:
        return (first,)
    if first in GROUPS and len(command) > 1 and command[1] in GROUPS[first]:
        return (first, command[1], "--help")
    return (first, "--help")
