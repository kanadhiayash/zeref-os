"""
CLI contract tests — every subcommand exits cleanly with predictable shape.
Run against the real checkout's CLI via `python3 -m shiroe`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        capture_output=True, text=True, cwd=str(cwd),
    )


def test_version_flag(repo_root: Path) -> None:
    r = _run(["--version"], repo_root)
    assert r.returncode == 0
    expected = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    assert expected in r.stdout


def test_help_lists_commands(repo_root: Path) -> None:
    r = _run(["--help"], repo_root)
    assert r.returncode == 0
    for cmd in ("status", "write-decision", "grade", "audit-privacy",
                "audit", "init", "db-status", "memory", "recall",
                "explain-search", "cost", "factguard", "evidence", "facts",
                "contradictions", "privacy", "route", "release", "doctor",
                "prompt", "handoff"):
        assert cmd in r.stdout, f"--help missing command {cmd!r}: {r.stdout}"
    assert "loop" not in r.stdout
    assert "team" not in r.stdout


def test_status_runs(repo_root: Path) -> None:
    r = _run(["status"], repo_root)
    assert r.returncode == 0, r.stderr
    # status prints section headers
    assert "memory/hot.md" in r.stdout
    assert "config/PROJECT.md" in r.stdout


def test_db_status_runs(repo_root: Path) -> None:
    r = _run(["db-status"], repo_root)
    assert r.returncode == 0, r.stderr
    assert "sqlite3" in r.stdout
    assert "Parquet" in r.stdout


def test_audit_runs(repo_root: Path) -> None:
    r = _run(["audit"], repo_root)
    # Validator may exit non-zero if there are real issues; we just require
    # the command to run end-to-end without crashing.
    assert r.returncode in (0, 1), (
        f"audit crashed: rc={r.returncode}\nstderr:\n{r.stderr}"
    )


def test_audit_privacy_runs(repo_root: Path, tmp_path: Path) -> None:
    # Point at empty tmp dir so we don't conflate with real memory state
    r = _run(["audit-privacy", "--directory", str(tmp_path)], repo_root)
    assert r.returncode == 0, (
        f"audit-privacy crashed: rc={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "Files scanned" in r.stdout


def test_grade_runs_with_claim(repo_root: Path) -> None:
    r = _run(["grade", "We shipped the migration today"], repo_root)
    assert r.returncode == 0, r.stderr
    assert "Grade:" in r.stdout
