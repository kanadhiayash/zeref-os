"""
Registry parity gate: every runtime entry resolves, every non-runtime entry
is honestly labeled.

Covers the two registry surfaces that describe different dimensions of Shiroe:
  * shiroe-registry.json — hand-authored (skills/agents/commands/team_packs/gates)
  * registry/components.json — generated (Python module ids)

Positive tests iterate the live registry and assert each entry either resolves
to an on-disk artifact or carries a non-active status. The negative test copies
the live registry, mutates one entry into an active-status claim on a
nonexistent path, and asserts scripts/shiroe-validate.py exits non-zero.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ACTIVE_STATUSES = {"runtime", "adapter"}
INACTIVE_STATUSES = {"contract", "experimental"}


def _module_resolves(root: Path, dotted: str) -> bool:
    rel = Path(*dotted.split("."))
    return (root / rel).is_dir() or (root / (str(rel) + ".py")).is_file()


@pytest.fixture(scope="module")
def registry(repo_root: Path) -> dict:
    return json.loads((repo_root / "shiroe-registry.json").read_text())


@pytest.fixture(scope="module")
def components(repo_root: Path) -> dict:
    return json.loads((repo_root / "registry" / "components.json").read_text())


def test_skills_resolve_or_are_labeled(repo_root: Path, registry: dict) -> None:
    for entry in registry["skills"]:
        name = entry["skill"]
        status = entry["status"]
        assert status in ACTIVE_STATUSES | INACTIVE_STATUSES, (
            f"skill {name!r} carries unknown status {status!r}"
        )
        if status in ACTIVE_STATUSES:
            assert (repo_root / "skills" / name).is_dir(), (
                f"skill {name!r} is active but skills/{name}/ is missing"
            )


@pytest.mark.parametrize("kind,id_key", [
    ("agents", "agent"),
    ("commands", "command"),
    ("team_packs", "pack"),
    ("gates", "gate"),
])
def test_pathed_entries_resolve_or_are_labeled(
    repo_root: Path, registry: dict, kind: str, id_key: str,
) -> None:
    for entry in registry[kind]:
        name = entry[id_key]
        status = entry["status"]
        assert status in ACTIVE_STATUSES | INACTIVE_STATUSES, (
            f"{kind[:-1]} {name!r} carries unknown status {status!r}"
        )
        path = entry["path"]
        if status in ACTIVE_STATUSES:
            assert (repo_root / path).is_file(), (
                f"{kind[:-1]} {name!r} is active but {path} is missing"
            )


def test_components_resolve_or_are_labeled(repo_root: Path, components: dict) -> None:
    for entry in components["components"]:
        cid = entry["id"]
        status = entry["status"]
        assert status in ACTIVE_STATUSES | INACTIVE_STATUSES, (
            f"component {cid!r} carries unknown status {status!r}"
        )
        if status in ACTIVE_STATUSES:
            assert _module_resolves(repo_root, cid), (
                f"component {cid!r} is active but no module resolves on disk"
            )


def test_validator_rejects_mislabeled_active_entry(
    repo_root: Path, tmp_path: Path,
) -> None:
    """Mutate a copy of shiroe-registry.json so one gate falsely claims runtime
    backing at a bogus path, feed it to the validator via --registry, and assert
    the exit code is non-zero. Uses the real repo tree for every other check so
    only the parity gate fails."""
    real = json.loads((repo_root / "shiroe-registry.json").read_text())
    real["gates"].append({
        "gate": "phantom-guard",
        "path": "shiroe/guards/phantom_guard.py",
        "status": "runtime",
    })
    broken = tmp_path / "shiroe-registry.broken.json"
    broken.write_text(json.dumps(real, indent=2))

    r = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "shiroe-validate.py"),
         "--registry", str(broken)],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert r.returncode != 0, (
        "validator accepted a gate that falsely claims runtime backing:\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "phantom-guard" in r.stdout or "phantom-guard" in r.stderr, (
        f"validator failed but did not name the mislabeled entry:\n{r.stdout}"
    )
