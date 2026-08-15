from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from shiroe.env import getenv
from shiroe.policy.loader import load_policy_stack
from shiroe.storage.state import DB_RELPATH, StateDB


RETIRED_FILES = (
    "shiroe/compat/legacy_identity.py",
    "shiroe/compat/__init__.py",
    "shiroe/memory_state.py",
    "shiroe/storage/importer.py",
    "shiroe/storage/legacy_receipt.py",
    "scripts/migrate-cards-to-atoms.py",
    "scripts/migrate-bitemporal-facts.py",
    "scripts/migrate-v3-to-v4.py",
    "scripts/migrate-v4.2-to-v4.3.py",
    "docs/DEPRECATIONS.md",
    "MIGRATION.md",
)


def _old_token(*parts: str) -> str:
    return "".join(parts)


def test_retired_compatibility_files_are_absent(repo_root: Path) -> None:
    missing = [rel for rel in RETIRED_FILES if (repo_root / rel).exists()]

    assert missing == []


@pytest.mark.parametrize(
    "module_name",
    (
        "shiroe.compat",
        "shiroe.compat.legacy_identity",
        "shiroe.memory_state",
        "shiroe.storage.importer",
        "shiroe.storage.legacy_receipt",
    ),
)
def test_retired_compatibility_modules_are_not_importable(
    repo_root: Path,
    module_name: str,
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    result = subprocess.run(
        [sys.executable, "-S", "-c", f"import {module_name}"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        env=env,
    )

    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr


def test_old_environment_prefix_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHIROE_ALLOW_NETWORK", raising=False)
    monkeypatch.setenv(_old_token("ZE", "REF", "_ALLOW_NETWORK"), "1")

    assert getenv("ALLOW_NETWORK", "fallback") == "fallback"


def test_old_workspace_policy_directory_is_ignored(tmp_path: Path) -> None:
    old_policy = tmp_path / _old_token(".ze", "ref") / "policy"
    old_policy.mkdir(parents=True)
    (old_policy / "deny.json").write_text('{"deny":["network"]}', encoding="utf-8")

    stack = load_policy_stack(tmp_path, global_root=tmp_path / "no-global")

    assert [layer.name for layer in stack] == ["runtime-invariant"]


def test_old_state_database_is_not_adopted(tmp_path: Path) -> None:
    old_db = tmp_path / "memory" / "state" / _old_token("ze", "ref", "2.sqlite")
    old_db.parent.mkdir(parents=True)
    conn = sqlite3.connect(old_db)
    conn.execute("CREATE TABLE marker (note TEXT)")
    conn.execute("INSERT INTO marker VALUES ('old state')")
    conn.commit()
    conn.close()

    StateDB(tmp_path)

    assert not (tmp_path / DB_RELPATH).exists()
