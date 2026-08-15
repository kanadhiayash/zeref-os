from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

PUBLIC_SURFACES = (
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
    "docs/DOCTOR.md",
    "docs/GETTING_STARTED.md",
    "docs/GLOSSARY.md",
    "docs/HARNESS_MATRIX.md",
    "docs/MEMORY_WRITES.md",
    "docs/PUBLIC_SAFE_COPY.md",
    "docs/PUBLIC_SURFACE.md",
    "docs/RELEASE_PROCESS.md",
    "docs/architecture/CORE_SCOPE.md",
    "docs/canon/PUBLIC_CLAIM_LEDGER.json",
    "docs/canon/SOURCE_AUTHORITY.md",
    "docs/wiki/Architecture.md",
    "docs/wiki/FAQ.md",
    "docs/wiki/Glossary.md",
    "docs/wiki/Home.md",
    "docs/wiki/Installation.md",
    "docs/wiki/Memory-Model.md",
    "docs/wiki/Privacy-Model.md",
    "docs/wiki/Stack.md",
    "memory/README.md",
    "references/harness-translation-map.md",
    "references/shared-anti-hallucination.md",
    "references/shiroe-qa-gate.md",
    "references/shiroe-safety-principles.md",
)

PRIVATE_NODE_PRACTICE = re.compile(
    r"\bnode\s*[01]\b|\btailscale\b|\bremote workers?\b|\btrusted workers?\b",
    re.IGNORECASE,
)


def test_public_surfaces_do_not_expose_private_node_practice() -> None:
    hits: list[str] = []
    for rel in PUBLIC_SURFACES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if PRIVATE_NODE_PRACTICE.search(line):
                hits.append(f"{rel}:{line_no}: {line.strip()}")

    assert not hits, "\n".join(hits)


def test_public_cli_help_does_not_advertise_private_node_practice() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "shiroe", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    text = result.stdout
    assert PRIVATE_NODE_PRACTICE.search(text) is None, text
    assert re.search(r"^\s+node\s+", text, re.MULTILINE) is None, text


def test_private_node_help_avoids_transport_branding() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "shiroe", "node", "register", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert PRIVATE_NODE_PRACTICE.search(result.stdout) is None, result.stdout
