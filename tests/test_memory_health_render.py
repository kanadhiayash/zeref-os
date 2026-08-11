from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _env(repo_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(repo_root: Path, cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=_env(repo_root),
    )


def _init(repo_root: Path, root: Path) -> None:
    result = _run(
        repo_root,
        repo_root,
        [
            "init",
            "--directory", str(root),
            "--name", "health-test",
            "--privacy", "abstract",
            "--tier", "auto",
            "--parent", "",
        ],
    )
    assert result.returncode == 0, result.stderr


def _add(repo_root: Path, root: Path, args: list[str]) -> dict:
    result = _run(repo_root, root, ["memory", "add", *args, "--json"])
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_memory_health_reports_findings(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)
    _add(
        repo_root,
        tmp_path,
        [
            "--type", "decision",
            "--claim", "Use deterministic token overlap before vector search.",
            "--source", "manual:test",
            "--evidence", "A",
            "--privacy", "public-safe",
        ],
    )
    _add(
        repo_root,
        tmp_path,
        [
            "--type", "decision",
            "--claim", "Use deterministic token overlap before vector search.",
            "--source", "manual:test-duplicate",
            "--evidence", "unverified",
        ],
    )

    health = _run(repo_root, tmp_path, ["memory", "health", "--json"])
    assert health.returncode == 0, health.stderr
    payload = json.loads(health.stdout)
    assert payload["summary"]["active_atoms"] == 2
    assert payload["duplicate_atoms"]
    assert payload["unsupported_atoms"]
    assert (tmp_path / "memory" / "reports" / "memory-health.json").is_file()
    assert (tmp_path / "memory" / "reports" / "memory-health.md").is_file()


def test_memory_refine_dry_run_does_not_write_report(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)
    _add(
        repo_root,
        tmp_path,
        [
            "--type", "fact",
            "--claim", "Benchmark score is maybe perfect.",
            "--source", "manual:test",
            "--evidence", "unverified",
        ],
    )

    refined = _run(repo_root, tmp_path, ["memory", "refine", "--dry-run", "--json"])
    assert refined.returncode == 0, refined.stderr
    payload = json.loads(refined.stdout)
    assert payload["dry_run"] is True
    assert payload["proposals"]
    assert not (tmp_path / "memory" / "reports" / "memory-health.json").exists()

    written = _run(repo_root, tmp_path, ["memory", "refine", "--json"])
    assert written.returncode == 0, written.stderr
    assert json.loads(written.stdout)["written"]["markdown"].endswith("memory-health.md")
    assert (tmp_path / "memory" / "reports" / "memory-health.md").is_file()


def test_memory_render_writes_views_without_touching_legacy(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)
    legacy_hot = tmp_path / "memory" / "hot.md"
    legacy_hot.write_text("# legacy hot\n\nDo not rewrite me.\n", encoding="utf-8")
    _add(
        repo_root,
        tmp_path,
        [
            "--type", "risk",
            "--claim", "Complete markdown rewrites are blocked by default.",
            "--source", "manual:test",
            "--evidence", "A",
            "--privacy", "public-safe",
            "--tag", "cost",
        ],
    )

    rendered = _run(repo_root, tmp_path, ["memory", "render", "all", "--json"])
    assert rendered.returncode == 0, rendered.stderr
    payload = json.loads(rendered.stdout)
    assert payload["view"] == "all"
    assert (tmp_path / "memory" / "views" / "hot.md").is_file()
    assert (tmp_path / "memory" / "views" / "RISKS.md").is_file()
    assert "Complete markdown rewrites" in (tmp_path / "memory" / "views" / "RISKS.md").read_text(encoding="utf-8")
    assert legacy_hot.read_text(encoding="utf-8") == "# legacy hot\n\nDo not rewrite me.\n"
