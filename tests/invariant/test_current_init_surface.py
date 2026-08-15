from __future__ import annotations

import subprocess
import sys
from pathlib import Path


RETIRED_INIT_SURFACES = (
    "config/BUDGET.md",
    "config/PARENT_SYNC.md",
    "config/PERMISSIONS.md",
    "memory/patterns",
    "memory/loops",
    "memory/layers",
    "memory/sync",
    "memory/state/events.jsonl",
    "memory/state/schema.json",
    "memory/state/" + "ze" + "ref.sqlite",
)


def test_current_init_surface_excludes_retired_runtime_paths(repo_root: Path, tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "shiroe",
            "init",
            str(tmp_path),
            "--name",
            "current-init",
            "--network-scope",
            "device-only",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env={"PYTHONPATH": str(repo_root)},
    )
    assert result.returncode == 0, result.stderr

    for retired in RETIRED_INIT_SURFACES:
        assert not (tmp_path / retired).exists(), f"retired init surface exists: {retired}"
