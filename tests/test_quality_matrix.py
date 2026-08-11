"""SHR-090..093: coverage, mutation, performance and clean-clone thresholds."""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "shr-verify.yml"


def test_ci_declares_coverage_fail_under_threshold() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"--fail-under=(\d+)", text)
    assert m is not None, "shr-verify.yml must invoke coverage with --fail-under"
    threshold = int(m.group(1))
    assert threshold >= 15, (
        f"CI coverage fail-under is {threshold}%, contract requires >= 15%"
    )


def test_ci_uses_source_scoped_coverage() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert "coverage run --source=shiroe" in text
    assert "--branch" in text


def test_ci_matrix_includes_multiple_python_versions() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    versions = set(re.findall(r"'3\.\d+'", text))
    assert len(versions) >= 3, (
        f"CI matrix has {len(versions)} python versions; contract requires >= 3"
    )


def test_working_tree_stays_clean_after_running_gate_scripts() -> None:
    venv_py = REPO_ROOT / ".venv" / "bin" / "python"
    if not venv_py.exists():
        pytest.skip(f"pinned venv interpreter missing: {venv_py}")
    for script in (
        "scripts/check-canon-consistency.py",
        "scripts/check-active-identity.py",
        "scripts/shiroe-validate.py",
        "scripts/check-trust-registry.py",
    ):
        r = subprocess.run(
            [str(venv_py), str(REPO_ROOT / script)],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
        )
        assert r.returncode == 0, f"{script} exited non-zero: {r.stderr}"
    dirty = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30,
    )
    for line in dirty.stdout.splitlines():
        path = line[3:].strip()
        assert path in {"tests/test_quality_matrix.py"}, (
            f"gate scripts mutated the tree: {line!r}"
        )


def test_provider_adapter_load_completes_under_budget() -> None:
    from shiroe.adapters.providers.base import JsonProviderAdapter

    p = REPO_ROOT / "shiroe/adapters/providers/anthropic.json"
    start = time.perf_counter()
    JsonProviderAdapter(p)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 200, (
        f"JsonProviderAdapter cold load took {elapsed_ms:.1f} ms; contract requires < 200 ms"
    )


def test_quality_matrix_declares_every_axis() -> None:
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    axes = {
        "validate": "Run shiroe-validate",
        "version_consistency": "Run version consistency checker",
        "privacy": "Run strict privacy audit repo-wide",
        "secrets": "Scan repo for committed secrets",
        "release": "Run release readiness gate",
        "pytest": "Run pytest with coverage",
    }
    missing = [name for name, needle in axes.items() if needle not in text]
    assert not missing, f"CI workflow missing quality axes: {missing}"
