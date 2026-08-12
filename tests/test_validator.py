"""
Drives scripts/shiroe-validate.py and asserts it passes on the current checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_validator_passes_on_clean_checkout(repo_root: Path) -> None:
    script = repo_root / "scripts" / "shiroe-validate.py"
    assert script.exists(), "scripts/shiroe-validate.py missing"
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert r.returncode == 0, (
        f"validator failed on clean checkout:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
