"""
`shiroe init` scaffolds only the current vNext runtime surface.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REQUIRED_DIRS = [
    "config",
    ".shiroe/policy",
    "memory/state",
]

REQUIRED_FILES = [
    "config/PROJECT.md",
    "PRIVACY.md",
    "REDACT.md",
    "SHARING_POLICY.md",
    ".shiroe/policy/defaults.json",
    "memory/state/shiroe.sqlite",
]

RETIRED_PATHS = [
    "config/BUDGET.md",
    "config/PARENT_SYNC.md",
    "config/PERMISSIONS.md",
    "memory/patterns/PATTERNS.jsonl",
    "memory/loops",
    "memory/layers/L0",
    "memory/layers/L1",
    "memory/layers/L2",
    "memory/layers/L3",
    "memory/sync/outbound",
    "memory/sync/parent",
    "memory/state/events.jsonl",
    "memory/state/schema.json",
    "memory/state/" + "ze" + "ref.sqlite",
]


def _run(repo_root: Path, cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env={"PYTHONPATH": str(repo_root)},
    )


def test_init_creates_only_current_runtime_surface(repo_root: Path, tmp_path: Path) -> None:
    result = _run(
        repo_root,
        repo_root,
        [
            "init",
            str(tmp_path),
            "--name",
            "scaffold-test",
            "--privacy",
            "abstract",
            "--network-scope",
            "device-only",
        ],
    )
    assert result.returncode == 0, result.stderr

    for directory in REQUIRED_DIRS:
        assert (tmp_path / directory).is_dir(), f"directory {directory!r} not created"

    for file in REQUIRED_FILES:
        assert (tmp_path / file).is_file(), f"file {file!r} not created"

    for retired in RETIRED_PATHS:
        assert not (tmp_path / retired).exists(), f"retired path {retired!r} was created"
    assert not (tmp_path / "memory" / "state" / "backups").exists()

    project = (tmp_path / "config" / "PROJECT.md").read_text(encoding="utf-8")
    assert "project_name: \"scaffold-test\"" in project
    assert "project_root: \"<discovered-at-runtime>\"" in project
    assert "privacy_mode" not in project
    assert "model_tier" not in project
    assert "parent_project" not in project
    assert "budget_warn_at" not in project
    assert "active_agents" not in project
    assert "active_skills" not in project

    privacy = (tmp_path / "PRIVACY.md").read_text(encoding="utf-8")
    assert "mode: abstract" in privacy
    assert "network_scope: device-only" in privacy

    policy = (tmp_path / ".shiroe" / "policy" / "defaults.json").read_text(encoding="utf-8")
    assert policy == '{"allow":["capability.invoke","subprocess"]}\n'


def test_init_rejects_retired_tier_and_parent_flags(repo_root: Path, tmp_path: Path) -> None:
    result = _run(
        repo_root,
        repo_root,
        [
            "init",
            str(tmp_path),
            "--name",
            "retired-flags",
            "--tier",
            "auto",
            "--parent",
            "",
        ],
    )
    assert result.returncode != 0
    assert "unrecognized arguments" in result.stderr


def test_init_accepts_network_scope_tailnet(repo_root: Path, tmp_path: Path) -> None:
    result = _run(
        repo_root,
        repo_root,
        [
            "init",
            str(tmp_path),
            "--name",
            "tailnet-scope",
            "--privacy",
            "exact",
            "--network-scope",
            "tailnet",
        ],
    )
    assert result.returncode == 0, result.stderr

    privacy = (tmp_path / "PRIVACY.md").read_text(encoding="utf-8")
    assert "mode: exact" in privacy
    assert "network_scope: tailnet" in privacy
