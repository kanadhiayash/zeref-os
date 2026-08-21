from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from shiroe.memory import scaffold_project
from shiroe.runtime.report import build_runtime_report

ROOT = Path(__file__).resolve().parents[2]

REQUIRED_TOP_KEYS = {
    "schema", "runtime", "project", "harness", "run", "capability",
    "approvals", "verification", "skills", "agents", "model", "routing",
    "provenance",
}


def _scaffold(tmp_path: Path) -> Path:
    project = tmp_path / "proj"
    scaffold_project(project, name="runtime-report-test", privacy="abstract", network_scope="device-only")
    return project


def test_runtime_report_has_every_schema_field(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    payload = build_runtime_report(root)

    assert payload["schema"] == "shiroe.runtime-update/v1"
    assert REQUIRED_TOP_KEYS <= payload.keys()
    assert payload["runtime"].keys() == {"version", "hash_chain"}
    assert payload["project"].keys() == {"root", "state_db_present"}
    assert payload["harness"].keys() == {"detected", "version", "level", "transport"}
    assert payload["run"].keys() == {"graph_id", "run_id", "node_id", "status"}
    assert payload["capability"].keys() == {"active_id", "lifecycle", "digest"}
    assert payload["approvals"].keys() == {"pending_count", "pending_ids"}
    assert payload["verification"].keys() == {"state"}
    assert payload["skills"].keys() == {"available", "active"}
    assert payload["agents"].keys() == {"active"}
    assert payload["routing"].keys() == {"intended", "actual", "provenance"}


def test_project_root_never_leaks_an_absolute_path(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    payload = build_runtime_report(root)

    assert not payload["project"]["root"].startswith("/")
    assert payload["project"]["root"] == root.name


def test_harness_degrades_to_unknown_when_nothing_is_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from shiroe.adapters.harnesses import base as harness_base

    monkeypatch.setattr(harness_base, "detect_all", lambda: [])
    root = _scaffold(tmp_path)

    payload = build_runtime_report(root)

    assert payload["harness"] == {
        "detected": "unknown",
        "version": "unknown",
        "level": "unknown",
        "transport": "unknown",
    }
    assert payload["provenance"]["harness"] == "unknown"


def test_skills_agents_and_model_are_always_unknown_from_the_shell_cli(tmp_path: Path) -> None:
    root = _scaffold(tmp_path)
    payload = build_runtime_report(root)

    assert payload["skills"] == {"available": "unknown", "active": "unknown"}
    assert payload["agents"] == {"active": "unknown"}
    assert payload["model"] is None
    assert payload["provenance"]["skills_active"] == "unknown"
    assert payload["provenance"]["agents_active"] == "unknown"
    assert payload["provenance"]["model"] == "unknown"


def _run_cli(cwd: Path, args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "shiroe", *args],
        cwd=cwd, env=env, text=True, capture_output=True,
    )


def test_status_json_without_runtime_flag_is_unchanged(tmp_path: Path) -> None:
    assert _run_cli(ROOT, ["init", str(tmp_path), "--name", "compat", "--privacy", "abstract"]).returncode == 0

    result = _run_cli(tmp_path, ["status", "--json"])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload.keys() == {"project_root", "state", "privacy"}
