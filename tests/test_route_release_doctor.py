"""Route, release, and doctor command tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from shiroe.release.checks import release_passed, run_release_check
from shiroe.release.doctor import doctor_passed, run_doctor
from shiroe.routing.policy import classify_task, validate_policy


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


def test_route_policy_classification() -> None:
    decision = classify_task("redact credentials before release")
    assert decision.domain == "security"
    assert decision.weight == "high"
    assert validate_policy() == []


def test_route_cli(repo_root: Path) -> None:
    classified = _run(repo_root, repo_root, ["route", "classify", "scan benchmark claims"])
    assert classified.returncode == 0
    assert json.loads(classified.stdout)["domain"] == "release"

    validate = _run(repo_root, repo_root, ["route", "policy", "validate"])
    assert validate.returncode == 0


def test_release_check(repo_root: Path) -> None:
    findings = run_release_check(repo_root)
    assert release_passed(findings)
    cli = _run(repo_root, repo_root, ["release", "check"])
    assert cli.returncode == 0, cli.stdout
    assert "benchmarks" not in cli.stdout.lower()


def test_doctor(repo_root: Path) -> None:
    checks = run_doctor(repo_root)
    assert doctor_passed(checks)
    cli = _run(repo_root, repo_root, ["doctor"])
    assert cli.returncode == 0, cli.stdout
    assert "PASS python" in cli.stdout
