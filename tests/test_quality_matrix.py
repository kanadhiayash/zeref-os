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
    thresholds = [int(m.group(1)) for m in re.finditer(r"--fail-under=(\d+)", text)]
    assert thresholds, "shr-verify.yml must invoke coverage with --fail-under"
    # Tiered coverage contract:
    #   - global line >= 70 via coverage.py --fail-under (measured baseline ~72-75%);
    #   - critical governance packages: line >= 90 AND branch >= 80, enforced
    #     independently by scripts/check-critical-coverage.py because coverage.py's
    #     single --fail-under cannot gate line and branch separately.
    assert min(thresholds) >= 70, (
        f"CI global coverage fail-under is {min(thresholds)}%, contract "
        "requires >= 70%"
    )
    assert "check-critical-coverage.py" in text, (
        "shr-verify.yml must enforce the critical-package coverage split gate "
        "via scripts/check-critical-coverage.py"
    )
    line_gate = re.search(r"--min-line\s+(\d+)", text)
    branch_gate = re.search(r"--min-branch\s+(\d+)", text)
    assert line_gate and int(line_gate.group(1)) >= 90, (
        "critical-package line coverage gate must be >= 90 "
        f"(found {line_gate.group(1) if line_gate else 'none'})"
    )
    assert branch_gate and int(branch_gate.group(1)) >= 80, (
        "critical-package branch coverage gate must be >= 80 "
        f"(found {branch_gate.group(1) if branch_gate else 'none'})"
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
    # The 'strict privacy audit repo-wide' step was retired in Phase 08
    # alongside its Phase-07-removed CLI backing (shiroe audit-privacy).
    # Credentials coverage remains via the grep-based 'Scan repo for
    # committed secrets' step. H7.2 re-introduces a vNext-native
    # release-readiness gate via scripts/release_ready.py.
    axes = {
        "validate": "Run shiroe-validate",
        "version_consistency": "Run version consistency checker",
        "secrets": "Scan repo for committed secrets",
        "pytest": "Run pytest with coverage",
        "release_readiness": "scripts/release_ready.py",
    }
    missing = [name for name, needle in axes.items() if needle not in text]
    assert not missing, f"CI workflow missing quality axes: {missing}"
