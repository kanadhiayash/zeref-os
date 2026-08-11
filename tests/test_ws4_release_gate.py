"""WS4 gate tests — release-gate integrity + init/doctor parity (issue #122).

Covers:
- fresh `shiroe init` scaffolds every file `shiroe doctor` requires;
- release check requires real commit provenance (fails without .git);
- file-based network permissions are consistent with the env lane and
  fail-closed by default.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from shiroe.memory import scaffold_project
from shiroe.release import checks as release_checks
from shiroe.release.checks import release_passed, run_release_check
from shiroe.release.doctor import doctor_passed, run_doctor
from shiroe.security.policy import (
    NetworkDeniedError,
    load_policy,
    require_network,
)


# ---------------------------------------------------------------------------
# Init / doctor parity
# ---------------------------------------------------------------------------

def test_fresh_init_passes_doctor(tmp_path: Path) -> None:
    scaffold_project(tmp_path, name="ws4", privacy="abstract", tier="auto", parent="")
    checks = run_doctor(tmp_path)
    failed = [(c.name, c.detail) for c in checks if c.status != "pass"]
    assert doctor_passed(checks), f"fresh init fails its own doctor: {failed}"


def test_init_creates_all_doctor_required_files(tmp_path: Path) -> None:
    scaffold_project(tmp_path, name="ws4", privacy="abstract", tier="auto", parent="")
    for rel in ("PRIVACY.md", "REDACT.md", "SHARING_POLICY.md",
                "config/PERMISSIONS.md", "config/PROJECT.md"):
        assert (tmp_path / rel).is_file(), f"init did not create {rel}"


def test_init_preserves_existing_policy_files(tmp_path: Path) -> None:
    sentinel = "# user-authored, do not clobber\n"
    (tmp_path / "REDACT.md").write_text(sentinel, encoding="utf-8")
    (tmp_path / "SHARING_POLICY.md").write_text(sentinel, encoding="utf-8")
    scaffold_project(tmp_path, name="ws4", privacy="abstract", tier="auto", parent="")
    assert (tmp_path / "REDACT.md").read_text(encoding="utf-8") == sentinel
    assert (tmp_path / "SHARING_POLICY.md").read_text(encoding="utf-8") == sentinel


# ---------------------------------------------------------------------------
# Commit provenance
# ---------------------------------------------------------------------------

def test_provenance_fails_outside_git_repo(tmp_path: Path) -> None:
    finding = release_checks._check_commit_provenance(tmp_path)
    assert finding.status == "fail"
    assert "SHA" in finding.reason


def test_provenance_passes_in_real_repo(repo_root: Path) -> None:
    finding = release_checks._check_commit_provenance(repo_root)
    assert finding.status == "pass", finding.reason


def test_evidence_blob_refused_without_sha(tmp_path: Path) -> None:
    release_checks._emit_release_evidence(tmp_path, [])
    evidence_dir = tmp_path / "docs" / "audits" / "release-evidence"
    assert not evidence_dir.exists(), "evidence must not be emitted with unknown SHA"


def test_release_check_fails_closed_without_git(tmp_path: Path) -> None:
    """End-to-end: release readiness still fails closed without commit provenance."""
    scaffold_project(tmp_path, name="ws4", privacy="abstract", tier="auto", parent="")
    findings = run_release_check(tmp_path)
    by_name = {f.name: f for f in findings}
    assert by_name["commit_provenance"].status == "fail"
    assert not release_passed(findings)


# ---------------------------------------------------------------------------
# Test-suite gate
# ---------------------------------------------------------------------------

def test_test_suite_gate_fails_without_tests_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    finding = release_checks._check_test_suite(tmp_path)
    assert finding.status == "fail"
    assert "tests/" in finding.reason


def test_test_suite_gate_nested_guard() -> None:
    assert os.environ.get("PYTEST_CURRENT_TEST"), "expected to run under pytest"
    finding = release_checks._check_test_suite(Path.cwd())
    assert finding.status == "pass"
    assert "active pytest run" in finding.reason


# ---------------------------------------------------------------------------
# File-based network permissions — consistent with env lane, fail-closed
# ---------------------------------------------------------------------------

def _write_privacy(root: Path, *, external: bool) -> None:
    root.joinpath("PRIVACY.md").write_text(
        f"---\nmode: exact\nexternal_transmission: {'on' if external else 'off'}\n---\n",
        encoding="utf-8",
    )


def test_network_denied_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    policy = load_policy(tmp_path)
    assert policy.network_denied is True
    with pytest.raises(NetworkDeniedError):
        require_network(policy, purpose="ws4-test")


def test_scaffolded_permissions_deny_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    scaffold_project(tmp_path, name="ws4", privacy="abstract", tier="auto", parent="")
    policy = load_policy(tmp_path)
    assert policy.network_denied is True


def test_file_lane_can_enable_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "PERMISSIONS.md").write_text(
        "---\ndefaults:\n  network:\n    - allowed\n---\n", encoding="utf-8",
    )
    _write_privacy(tmp_path, external=True)
    policy = load_policy(tmp_path)
    assert policy.network_denied is False
    require_network(policy, purpose="ws4-test")  # must not raise


def test_file_lane_requires_privacy_consent_too(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "PERMISSIONS.md").write_text(
        "---\ndefaults:\n  network:\n    - allowed\n---\n", encoding="utf-8",
    )
    _write_privacy(tmp_path, external=False)
    policy = load_policy(tmp_path)
    with pytest.raises(NetworkDeniedError):
        require_network(policy, purpose="ws4-test")


def test_file_lane_explicit_denied_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "PERMISSIONS.md").write_text(
        "---\ndefaults:\n  network:\n    - denied\n    - allowed\n---\n",
        encoding="utf-8",
    )
    policy = load_policy(tmp_path)
    assert policy.network_denied is True


def test_env_lane_still_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHIROE_ALLOW_NETWORK", "1")
    policy = load_policy(tmp_path)
    require_network(policy, purpose="ws4-test")  # env lane authorizes
