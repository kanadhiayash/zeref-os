"""SHR-032 — the active-surface identity guard.

`scripts/check-active-identity.py` fails when a retired identity reference
appears on a surface that is supposed to be Shiroe-named, and passes only on
narrow historical or private evidence paths that are supposed to keep old names.

The synthetic-injection tests are the point of the file: a guard nobody has
watched fail is a guard nobody knows works.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-active-identity.py"


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True, text=True,
    )


def _seed(root: Path) -> None:
    """A minimal tree the scanner recognises, with no legacy references."""
    (root / "shiroe").mkdir(parents=True, exist_ok=True)
    (root / "shiroe" / "cli.py").write_text("# shiroe cli\n", encoding="utf-8")
    (root / "README.md").write_text("# Shiroe\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# The real tree
# --------------------------------------------------------------------------- #

def test_repo_tree_is_clean() -> None:
    result = _run(REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr


def test_workflow_display_names_are_shiroe_named() -> None:
    for name in ("shr-verify.yml", "branch-retention.yml"):
        first = (REPO_ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8").splitlines()[0]
        assert "ZRF" not in first and "Zeref" not in first, first


# --------------------------------------------------------------------------- #
# Synthetic injection — the guard must actually bite
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "rel, body",
    [
        ("shiroe/newmod.py", 'LEGACY = "zeref"\n'),
        ("README.md", "Install Zeref today.\n"),
        (".github/workflows/ci.yml", "name: ZRF Build\n"),
        ("registry/thing.json", '{"id": "zrf-thing"}\n'),
        ("missions/new.yaml", "id: zeref\n"),
    ],
)
def test_injected_active_reference_fails(tmp_path: Path, rel: str, body: str) -> None:
    _seed(tmp_path)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert rel in result.stdout + result.stderr


def test_allowlisted_paths_pass(tmp_path: Path) -> None:
    _seed(tmp_path)
    for rel, body in [
        ("CHANGELOG.md", "Renamed Zeref to Shiroe.\n"),
        ("docs/archive/old.md", "Zeref OS v4.\n"),
        ("docs/adr/ADR-0009-x.md", "The zeref.sqlite store.\n"),
        ("tests/fixtures/legacy/x.json", '{"n": "zeref"}\n'),
        ("memory/state/legacy-closure-receipts/local.json", '{"path": "memory/state/zeref.sqlite"}\n'),
        ("memory/state/legacy-closure-backups/local/source.json", '{"legacy": "ZEREF_HOME"}\n'),
    ]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_clean_tree_passes(tmp_path: Path) -> None:
    _seed(tmp_path)
    assert _run(tmp_path).returncode == 0


def test_missing_root_exits_two(tmp_path: Path) -> None:
    result = _run(tmp_path / "nope")
    assert result.returncode == 2


# --------------------------------------------------------------------------- #
# The allowlist must stay a reviewed list, not a blanket
# --------------------------------------------------------------------------- #

def test_every_allowlist_entry_states_a_reason() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("_cai", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    assert module.ALLOWLIST, "allowlist is empty"
    for path, reason in module.ALLOWLIST.items():
        assert reason.strip(), f"{path} has no reason"
        assert path not in ("", "/", "**", "*"), f"{path} is a blanket allow"
        assert not path.startswith("shiroe/**"), f"{path} allows all of shiroe/"


def test_json_report_lists_findings(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "shiroe" / "bad.py").write_text('X = "Zeref"\n', encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--json"],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["findings"], payload
    assert payload["findings"][0]["path"] == "shiroe/bad.py"
