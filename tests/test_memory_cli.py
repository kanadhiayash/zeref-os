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
            "--name", "memory-cli-test",
            "--privacy", "abstract",
            str(root),
        ],
    )
    assert result.returncode == 0, result.stderr


def test_memory_write_list_supersede_round_trip(repo_root: Path, tmp_path: Path) -> None:
    _init(repo_root, tmp_path)

    payload = {
        "type": "decision",
        "title": "recall preference",
        "claim": "Use deterministic token overlap before optional vector search.",
        "summary": "Prefer stdlib SQLite for recall.",
        "privacy_class": "public-safe",
        "evidence_grade": "A",
        "source_refs": ["manual:test"],
    }
    (tmp_path / "decision.json").write_text(json.dumps(payload), encoding="utf-8")

    write = _run(repo_root, tmp_path, ["memory", "write", "--from", "decision.json", "--json"])
    assert write.returncode == 0, write.stderr
    record = json.loads(write.stdout)
    assert record["type"] == "decision"

    listed = _run(repo_root, tmp_path, ["memory", "list", "--json"])
    assert listed.returncode == 0, listed.stderr
    ids = [row["id"] for row in json.loads(listed.stdout)]
    assert record["id"] in ids

    replacement_payload = {
        "type": "decision",
        "title": "recall preference (revised)",
        "claim": "Vector search stays optional; deterministic overlap is primary.",
        "summary": "Revised: stdlib SQLite remains the sole recall path.",
        "privacy_class": "public-safe",
        "evidence_grade": "A",
        "source_refs": ["manual:test"],
    }
    (tmp_path / "revised.json").write_text(json.dumps(replacement_payload), encoding="utf-8")
    revised = _run(repo_root, tmp_path, ["memory", "write", "--from", "revised.json", "--json"])
    assert revised.returncode == 0, revised.stderr
    replacement_id = json.loads(revised.stdout)["id"]

    superseded = _run(
        repo_root,
        tmp_path,
        ["memory", "supersede", record["id"], "--with", replacement_id],
    )
    assert superseded.returncode == 0, superseded.stderr

    shown = _run(repo_root, tmp_path, ["memory", "show", record["id"], "--json"])
    assert shown.returncode == 0, shown.stderr
    assert json.loads(shown.stdout)["status"] == "superseded"
