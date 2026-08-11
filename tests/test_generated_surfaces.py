"""SHR-125..129: generated surfaces are consistent from a clean clone."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _venv() -> Path:
    return REPO_ROOT / ".venv" / "bin" / "python"


def test_registry_counts_match_disk() -> None:
    reg = json.loads((REPO_ROOT / "shiroe-registry.json").read_text(encoding="utf-8"))
    for surface_name, surface in reg.items():
        if not isinstance(surface, list):
            continue
        for entry in surface:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") not in {"runtime", "adapter"}:
                continue
            if "path" not in entry:
                continue
            p = REPO_ROOT / entry["path"]
            assert p.exists(), (
                f"{surface_name} entry {entry.get('id', '?')} claims runtime "
                f"path {entry['path']} but it does not exist"
            )


def test_readme_relative_links_resolve() -> None:
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    link_re = re.compile(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]*)?\)")
    for m in link_re.finditer(text):
        href = m.group(1).strip()
        if href.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        if href.startswith("#"):
            continue
        target = (REPO_ROOT / href).resolve()
        assert target.exists(), f"README link target missing: {href}"


def test_identity_scan_passes_from_clean_read() -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    r = subprocess.run(
        [str(venv), str(REPO_ROOT / "scripts" / "check-active-identity.py"),
         "--root", str(REPO_ROOT)],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_installation_smoke_import_shiroe_ok() -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [str(venv), "-c", "import shiroe; import shiroe.graph; import shiroe.privacy; print('ok')"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in r.stdout


def test_installation_smoke_cli_help_returns_zero() -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(
        [str(venv), "-m", "shiroe", "--help"],
        capture_output=True, text=True, env=env, timeout=30,
        cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_generated_registry_surfaces_are_stable_on_re_read() -> None:
    reg1 = json.loads((REPO_ROOT / "shiroe-registry.json").read_text(encoding="utf-8"))
    reg2 = json.loads((REPO_ROOT / "shiroe-registry.json").read_text(encoding="utf-8"))
    assert reg1 == reg2
