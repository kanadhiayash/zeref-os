"""
Drives scripts/check-version-consistency.py against the real repo and asserts
every public version surface agrees with shiroe/VERSION.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def test_canonical_version_file_is_semver(repo_root: Path) -> None:
    v = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    assert re.match(r"^\d+\.\d+\.\d+(?:[-+][\w.\-]+)?$", v), (
        f"shiroe/VERSION '{v}' is not SemVer"
    )


def test_consistency_script_exits_clean(repo_root: Path) -> None:
    script = repo_root / "scripts" / "check-version-consistency.py"
    assert script.exists(), "scripts/check-version-consistency.py is missing"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(repo_root)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"version drift detected:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_runtime_version_matches_file(repo_root: Path) -> None:
    expected = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    sys.path.insert(0, str(repo_root))
    import shiroe  # noqa: WPS433
    assert shiroe.__version__ == expected


def test_pyproject_matches_file(repo_root: Path) -> None:
    expected = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    text = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
    assert m and m.group(1) == expected


def test_plugin_manifest_matches_file(repo_root: Path) -> None:
    expected = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    data = json.loads((repo_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data["version"] == expected
