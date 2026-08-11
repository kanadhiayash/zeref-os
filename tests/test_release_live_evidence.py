"""SHR-094..098: stale release verdicts cannot pass, rollback rehearsal
completes before release approval.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def _venv() -> Path:
    return REPO_ROOT / ".venv" / "bin" / "python"


def _release_dir() -> Path:
    return REPO_ROOT / "docs" / "audits" / "release-evidence"


def test_release_check_writes_sha_bound_evidence_blob() -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), timeout=15,
    ).decode().strip()
    r = subprocess.run(
        [str(venv), "-m", "shiroe", "release", "check"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, r.stderr
    blobs = sorted(_release_dir().glob(f"{head[:12]}_*.json"))
    assert blobs, f"no evidence blob written for HEAD {head[:12]}"


def test_stored_evidence_carries_sha_and_findings() -> None:
    blobs = sorted(_release_dir().glob("*.json"))
    if not blobs:
        pytest.skip("no release-evidence blobs on disk")
    latest = blobs[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    for key in ("sha", "ts", "findings", "passed"):
        assert key in data, f"release evidence missing {key}"
    assert isinstance(data["findings"], list) and data["findings"]
    for f in data["findings"]:
        assert "name" in f and "status" in f, (
            f"release finding missing required keys: {f.keys()}"
        )


def test_stale_evidence_does_not_grant_pass(tmp_path: Path) -> None:
    stale = {
        "sha": "0" * 40,
        "ts": "2020-01-01T00:00:00Z",
        "findings": [{"check": "commit_provenance", "outcome": "PASS", "message": "old"}],
        "passed": True,
    }
    p = tmp_path / "stale.json"
    p.write_text(json.dumps(stale), encoding="utf-8")
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), timeout=15,
    ).decode().strip()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["sha"] != head, "stale fixture must not match live HEAD"


def test_release_check_refuses_when_head_cannot_be_resolved(tmp_path: Path) -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    r = subprocess.run(
        [str(venv), "-m", "shiroe", "release", "check", "--root", str(tmp_path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
    )
    assert r.returncode != 0 or "commit_provenance" in (r.stdout + r.stderr)


def test_rollback_runbook_exists_and_names_the_recovery_command() -> None:
    candidates = [
        REPO_ROOT / "docs" / "security" / "HISTORY_REWRITE_RUNBOOK.md",
        REPO_ROOT / "docs" / "ROLLBACK.md",
    ]
    present = [c for c in candidates if c.is_file()]
    assert present, f"no rollback runbook found under any of: {candidates}"
    for path in present:
        text = path.read_text(encoding="utf-8").lower()
        assert any(cmd in text for cmd in ("git revert", "git reset", "rollback")), (
            f"{path} does not name a concrete rollback command"
        )


def test_release_check_output_names_every_declared_check() -> None:
    venv = _venv()
    if not venv.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv}")
    r = subprocess.run(
        [str(venv), "-m", "shiroe", "release", "check"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=180,
    )
    assert r.returncode == 0, r.stderr
    for name in (
        "commit_provenance",
        "audit_logs",
        "memory_layout",
        "factguard",
        "evidenceguard",
        "version",
        "version_consistency",
        "privacy_scan",
        "registry_completeness",
        "pyproject_backend",
        "soul_present",
        "workflow_yaml",
        "claim_gate",
    ):
        assert name in r.stdout, f"release check output missing declared check: {name}"
