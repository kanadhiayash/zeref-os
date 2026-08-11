"""SHR-077..080: trust registry covers every public visual + imported reference."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check-trust-registry.py"
VENV_PY = REPO_ROOT / ".venv" / "bin" / "python"
if not VENV_PY.exists():
    pytest.skip(f"pinned venv interpreter missing: {VENV_PY}", allow_module_level=True)
PY = str(VENV_PY)
TIMEOUT_S = 60


def _run(root: Path, registry: Path | None = None) -> subprocess.CompletedProcess:
    args = [PY, str(SCRIPT), "--root", str(root)]
    if registry is not None:
        args += ["--registry", str(registry)]
    return subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT_S)


def test_real_tree_passes() -> None:
    r = _run(REPO_ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Trust registry passed" in r.stdout


def test_unregistered_visual_fails(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "phantom.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (tmp_path / "docs" / "canon").mkdir(parents=True)
    (tmp_path / "docs" / "canon" / "TRUST_REGISTRY.json").write_text(
        json.dumps({"schema_version": "1", "public_visuals": [], "imported_references": []}),
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "phantom.png" in r.stdout
    assert "no TRUST_REGISTRY entry" in r.stdout


def test_unregistered_reference_fails(tmp_path: Path) -> None:
    (tmp_path / "docs" / "canon").mkdir(parents=True)
    (tmp_path / "docs" / "canon" / "TRUST_REGISTRY.json").write_text(
        json.dumps({"schema_version": "1", "public_visuals": [], "imported_references": []}),
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "See https://example.com/unapproved-source for details.\n",
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "example.com/unapproved-source" in r.stdout


def test_shields_io_reference_is_approved_by_pattern(tmp_path: Path) -> None:
    (tmp_path / "docs" / "canon").mkdir(parents=True)
    shutil.copy(
        REPO_ROOT / "docs/canon/TRUST_REGISTRY.json",
        tmp_path / "docs/canon/TRUST_REGISTRY.json",
    )
    (tmp_path / "README.md").write_text(
        "![badge](https://img.shields.io/badge/status-green-brightgreen)\n",
        encoding="utf-8",
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_registry_fails(tmp_path: Path) -> None:
    r = _run(tmp_path, registry=tmp_path / "missing.json")
    assert r.returncode == 1
    assert "trust registry missing" in r.stderr


def test_registry_schema_has_every_visual_field() -> None:
    reg = json.loads((REPO_ROOT / "docs/canon/TRUST_REGISTRY.json").read_text(encoding="utf-8"))
    required = {"path", "kind", "rights_status", "approved_source", "approved_by", "approved_at"}
    for v in reg["public_visuals"]:
        assert required <= set(v), f"visual missing fields: {required - set(v)} in {v}"


def test_registry_schema_has_every_reference_field() -> None:
    reg = json.loads((REPO_ROOT / "docs/canon/TRUST_REGISTRY.json").read_text(encoding="utf-8"))
    required = {"url_pattern", "kind", "rights_status", "approved_source", "approved_by", "approved_at"}
    for r in reg["imported_references"]:
        assert required <= set(r), f"reference missing fields: {required - set(r)} in {r}"


def test_rights_status_values_are_from_enum() -> None:
    reg = json.loads((REPO_ROOT / "docs/canon/TRUST_REGISTRY.json").read_text(encoding="utf-8"))
    allowed = set(reg["rights_statuses"])
    for entry in reg["public_visuals"] + reg["imported_references"]:
        assert entry["rights_status"] in allowed, (
            f"unknown rights_status {entry['rights_status']!r}; allowed: {allowed}"
        )
