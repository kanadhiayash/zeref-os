"""
Drives scripts/check-version-consistency.py against the real repo and asserts
every public version surface agrees with shiroe/VERSION.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


def _load_checker_module(repo_root: Path):
    """Import scripts/check-version-consistency.py as a module (hyphenated filename)."""
    script = repo_root / "scripts" / "check-version-consistency.py"
    spec = importlib.util.spec_from_file_location("check_version_consistency", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_classifier_for_version_maps_prerelease_label_to_dev_status(repo_root: Path) -> None:
    """SHR-13 regression: the checker must tie the trove Development Status
    classifier to the pre-release label of shiroe/VERSION (-alpha -> "3 - Alpha",
    -beta -> "4 - Beta", no pre-release -> "4 - Beta" or "5 - Production/Stable").
    """
    checker = _load_checker_module(repo_root)
    assert checker._classifier_for_version("3.0.0-alpha.1") == {"3 - Alpha"}
    assert checker._classifier_for_version("3.0.0-beta.2") == {"4 - Beta"}
    assert checker._classifier_for_version("3.0.0") == {"4 - Beta", "5 - Production/Stable"}


def test_consistency_checker_flags_classifier_mismatch(repo_root: Path, tmp_path: Path) -> None:
    """The checker rule itself must detect a Development Status classifier that
    disagrees with the VERSION pre-release label, not just the version string."""
    checker = _load_checker_module(repo_root)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nclassifiers = [\n    "Development Status :: 4 - Beta",\n]\n',
        encoding="utf-8",
    )
    _name, _expected_desc, observed = checker._check_dev_status_classifier(tmp_path, "3.0.0-alpha.1")
    assert observed == "4 - Beta"
    assert observed not in checker._classifier_for_version("3.0.0-alpha.1")


def test_pyproject_classifier_matches_version_prerelease_label(repo_root: Path) -> None:
    """Real-repo regression: pyproject.toml's Development Status classifier must
    match the current shiroe/VERSION pre-release label."""
    checker = _load_checker_module(repo_root)
    version = (repo_root / "shiroe" / "VERSION").read_text(encoding="utf-8").strip()
    _name, expected_desc, observed = checker._check_dev_status_classifier(repo_root, version)
    allowed = checker._classifier_for_version(version)
    assert observed in allowed, (
        f"pyproject.toml Development Status classifier {observed!r} does not match "
        f"VERSION {version!r}; expected one of {sorted(allowed)} ({expected_desc})"
    )


def test_consistency_script_flags_classifier_mismatch_via_cli(repo_root: Path) -> None:
    """End-to-end: running check-version-consistency.py must exit nonzero when
    the classifier disagrees with VERSION's pre-release label (the real bug this
    regression rule was written for: 3.0.0-alpha.1 paired with "4 - Beta")."""
    scratch = _scratch_repo_for_classifier_check(repo_root)
    (scratch / "shiroe" / "VERSION").write_text("3.0.0-alpha.1\n", encoding="utf-8")
    text = (scratch / "pyproject.toml").read_text(encoding="utf-8")
    mismatched = re.sub(
        r'"Development Status :: [^"]+"',
        '"Development Status :: 4 - Beta"',
        text,
    )
    (scratch / "pyproject.toml").write_text(mismatched, encoding="utf-8")
    script = repo_root / "scripts" / "check-version-consistency.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(scratch)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, (
        f"checker should have flagged classifier drift:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def _scratch_repo_for_classifier_check(repo_root: Path):
    """Build a minimal on-disk copy of the surfaces check-version-consistency.py
    reads, so the classifier rule can be exercised end-to-end via the CLI without
    depending on unrelated repo state."""
    import shutil
    import tempfile

    scratch = Path(tempfile.mkdtemp(prefix="shr-classifier-check-"))
    for rel in (
        "shiroe/VERSION",
        "shiroe/__init__.py",
        "shiroe/IDENTITY.json",
        "pyproject.toml",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "docs/wiki/Installation.md",
        "SKILL.md",
        ".github/CODEOWNERS",
    ):
        src = repo_root / rel
        dst = scratch / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return scratch
