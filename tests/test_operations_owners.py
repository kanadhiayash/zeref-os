"""SHR-130..136: docs/OPERATIONS.md rows have owner + cadence; superseded
material stays out of current navigation."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OPS = REPO_ROOT / "docs" / "OPERATIONS.md"


def _rows(text: str) -> list[list[str]]:
    lines = text.splitlines()
    table: list[list[str]] = []
    in_table = False
    for line in lines:
        if line.startswith("| Surface |"):
            in_table = True
            continue
        if in_table:
            if not line.startswith("|"):
                break
            if re.match(r"\|[-|\s]+\|", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            table.append(cells)
    return table


def test_operations_doc_exists() -> None:
    assert OPS.is_file()


def test_every_row_has_an_owner_and_cadence() -> None:
    text = OPS.read_text(encoding="utf-8")
    rows = _rows(text)
    assert rows, "no maintenance-surface table rows found"
    for row in rows:
        assert len(row) >= 4, f"row too short: {row}"
        surface, owner, cadence, look = row[:4]
        assert surface, f"row missing surface: {row}"
        assert owner and owner not in {"TODO", "TBD", "-", "?"}, (
            f"row missing owner: {row}"
        )
        assert cadence and cadence not in {"TODO", "TBD", "-", "?"}, (
            f"row missing cadence: {row}"
        )
        assert look, f"row missing 'Where to look' entry: {row}"


def test_superseded_paths_are_declared() -> None:
    text = OPS.read_text(encoding="utf-8")
    assert "Superseded surfaces" in text
    assert re.search(r"- `[^`]+`", text)


def test_current_navigation_does_not_link_superseded() -> None:
    text = OPS.read_text(encoding="utf-8")
    section = text.split("Superseded surfaces", 1)[-1].split("##", 1)[0]
    superseded = set(re.findall(r"- `([^`]+)`", section))
    superseded = {s for s in superseded if not s.endswith("/")}
    nav_files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "GETTING_STARTED.md",
    ]
    for nav in nav_files:
        if not nav.is_file():
            continue
        nav_text = nav.read_text(encoding="utf-8")
        for path in superseded:
            assert path not in nav_text, (
                f"{nav.name} links to superseded path {path!r}; remove or annotate"
            )


def test_every_gate_script_named_in_operations_exists() -> None:
    text = OPS.read_text(encoding="utf-8")
    for script in (
        "scripts/check-canon-consistency.py",
        "scripts/check-active-identity.py",
        "scripts/shiroe-validate.py",
        "scripts/check-version-consistency.py",
        "scripts/check-trust-registry.py",
    ):
        assert script in text, f"OPERATIONS.md must name gate script {script}"
        assert (REPO_ROOT / script).is_file(), f"named gate script missing: {script}"


def test_rollback_runbook_is_referenced_and_present() -> None:
    text = OPS.read_text(encoding="utf-8")
    assert "docs/security/HISTORY_REWRITE_RUNBOOK.md" in text
    assert (REPO_ROOT / "docs" / "security" / "HISTORY_REWRITE_RUNBOOK.md").is_file()
