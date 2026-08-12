"""
`shiroe init` scaffolds the expected layout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from shiroe.memory import MEMORY_DIRS, MEMORY_FILES, PROJECT_DIRS


REQUIRED_DIRS = [
    *MEMORY_DIRS,
    *PROJECT_DIRS,
]

REQUIRED_FILES = [
    "config/PROJECT.md",
    "config/BUDGET.md",
    "PRIVACY.md",
    *MEMORY_FILES,
]


def test_init_scaffolds_full_layout(repo_root: Path, tmp_path: Path) -> None:
    r = subprocess.run(
        [sys.executable, "-m", "shiroe", "init",
         "--name", "scaffold-test",
         "--privacy", "abstract",
         "--tier", "auto",
         "--parent", "",
         str(tmp_path)],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert r.returncode == 0, (
        f"init crashed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )

    for d in REQUIRED_DIRS:
        assert (tmp_path / d).is_dir(), f"directory {d!r} not created"

    for f in REQUIRED_FILES:
        assert (tmp_path / f).is_file(), f"file {f!r} not created"

    project = (tmp_path / "config" / "PROJECT.md").read_text(encoding="utf-8")
    assert "scaffold-test" in project
    assert "privacy_mode: abstract" in project
    assert "model_tier: auto" in project
