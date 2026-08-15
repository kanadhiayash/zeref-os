"""Append-only audit log tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shiroe.audit.logger import AuditLogger
from shiroe.audit.reports import audit_report
from shiroe.memory import scaffold_project


def _env(repo_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(repo_root: Path, cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=_env(repo_root),
    )


def _init(root: Path) -> None:
    (root / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")
    scaffold_project(root, name="audit", privacy="abstract", network_scope="device-only")


def test_audit_logger_creates_append_only_log_and_schema(tmp_path: Path) -> None:
    _init(tmp_path)
    logger = AuditLogger.from_root(tmp_path)
    event = logger.append(
        event_type="memory_write",
        status="accepted",
        reason="accepted guarded write",
        file="proposal.json",
        memory_id="mem_2026_07_09_0001",
        guards_run=["factguard"],
    )
    logger.append(
        event_type="memory_write",
        status="blocked",
        reason="blocked guarded write",
        file="proposal.json",
        guards_run=["factguard"],
    )

    lines = (tmp_path / "memory" / "audit" / "writes.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    payload = json.loads(lines[0])
    assert payload["event_id"] == event.event_id
    assert payload["event_type"] == "memory_write"
    assert payload["status"] == "accepted"
    assert payload["actor"] == "shiroe"
    assert payload["guards_run"] == ["factguard"]


@pytest.mark.skip(
    reason="Phase 07 CLI redesign dropped the CLI-driven audit-emit path. "
    "AuditLogger direct-invocation coverage is above; CLI-integrated "
    "audit emission is post-vNext follow-up (see docs/architecture/REMOVALS.md Phase 08)."
)
def test_guarded_write_logs_accepted_and_rejected_audit_events(repo_root: Path, tmp_path: Path) -> None:
    result = _run(
        repo_root,
        repo_root,
        [
            "init",
            "--name",
            "audit-cli",
            "--privacy",
            "abstract",
            str(tmp_path),
        ],
    )
    assert result.returncode == 0, result.stderr

    valid = {
        "type": "decision",
        "title": "audit write",
        "claim": "Audit writes are recorded.",
        "privacy_class": "internal",
        "evidence_grade": "B",
        "source_refs": ["README.md"],
    }
    invalid = {**valid, "privacy_class": "secret"}
    (tmp_path / "valid.json").write_text(json.dumps(valid), encoding="utf-8")
    (tmp_path / "invalid.json").write_text(json.dumps(invalid), encoding="utf-8")

    assert _run(repo_root, tmp_path, ["memory", "write", "--from", "valid.json"]).returncode == 0
    assert _run(repo_root, tmp_path, ["memory", "write", "--from", "invalid.json"]).returncode == 1

    writes = (tmp_path / "memory" / "audit" / "writes.jsonl").read_text(encoding="utf-8")
    failures = (tmp_path / "memory" / "audit" / "guard_failures.jsonl").read_text(encoding="utf-8")
    assert "accepted guarded write" in writes
    assert "privacy_class `secret` cannot be stored" in writes
    assert "PrivacyGuard" in failures or "privacy_class `secret`" in failures


def test_audit_report_and_corrupt_jsonl_handling(repo_root: Path, tmp_path: Path) -> None:
    _init(tmp_path)
    logger = AuditLogger.from_root(tmp_path)
    logger.append(event_type="memory_write", status="accepted", reason="ok")
    logger.append(event_type="guard_failure", status="blocked", reason="bad")
    with (tmp_path / "memory" / "audit" / "writes.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("{not-json}\n")

    text = audit_report(tmp_path)
    assert "Memory writes accepted: 1" in text
    assert "Guard failures: 1" in text
    assert "Corrupt JSONL lines: 1" in text
