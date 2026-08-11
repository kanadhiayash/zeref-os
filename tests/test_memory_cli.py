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
            "--name", "memory-cli-test",
            "--privacy", "abstract",
            "--tier", "auto",
            "--parent", "",
        ],
    )
    assert result.returncode == 0, result.stderr


def test_memory_add_list_patch_round_trip(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)

    add = _run(
        repo_root,
        tmp_path,
        [
            "memory", "add",
            "--type", "decision",
            "--claim", "Use deterministic token overlap before optional vector search.",
            "--summary", "Prefer stdlib SQLite for recall.",
            "--source", "manual:test",
            "--source-type", "manual",
            "--evidence", "A",
            "--confidence", "high",
            "--privacy", "public-safe",
            "--tag", "recall",
            "--json",
        ],
    )
    assert add.returncode == 0, add.stderr
    atom = json.loads(add.stdout)
    assert atom["type"] == "decision"
    assert atom["tags"] == ["recall"]

    listed = _run(repo_root, tmp_path, ["memory", "list", "--type", "decision", "--json"])
    assert listed.returncode == 0, listed.stderr
    assert json.loads(listed.stdout)[0]["id"] == atom["id"]

    patched = _run(
        repo_root,
        tmp_path,
        ["memory", "patch", atom["id"], "--status", "superseded", "--json"],
    )
    assert patched.returncode == 0, patched.stderr
    assert json.loads(patched.stdout)["status"] == "superseded"


def test_memory_add_scrubs_credentials(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)

    result = _run(
        repo_root,
        tmp_path,
        [
            "memory", "add",
            "--type", "risk",
            "--claim", "Rotate secret key fakecredential123",
            "--source", "manual:test",
            "--json",
        ],
    )
    assert result.returncode == 0, result.stderr
    atom = json.loads(result.stdout)
    assert "fakecredential123" not in atom["claim"]
    assert "[REDACTED:credentials]" in atom["claim"]
