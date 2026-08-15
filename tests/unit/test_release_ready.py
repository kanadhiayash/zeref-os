"""H7.1: shape test for scripts/release_ready.py.

We do NOT actually execute the release-readiness gate here (that would
loop pytest inside pytest). We assert:
  - the script exists and is Python-importable;
  - CHECKS names the expected surviving vNext invariants;
  - every command is repo-relative and does not shell out to network.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "release_ready.py"


def _load():
    spec = importlib.util.spec_from_file_location("shiroe_release_ready", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["shiroe_release_ready"] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_script_exists_and_imports():
    assert SCRIPT.exists()
    module = _load()
    assert hasattr(module, "CHECKS")
    assert hasattr(module, "main")


def test_checks_cover_surviving_vnext_invariants():
    module = _load()
    names = [name for name, _cmd in module.CHECKS]
    required = [
        "pytest-full",
        "shiroe-validate",
        "canon-consistency",
        "active-identity",
        "version-consistency",
        "trust-registry",
        "doctor",
        "verify-runtime",
        "state-verify",
        "invariant-suite",
        "fresh-init-contract",
        "docs-command-parser",
        "node-schema-lease-transport",
        "benchmark-entry-status",
    ]
    missing = set(required) - set(names)
    assert not missing, f"release_ready missing required checks: {sorted(missing)}"
    assert names == required


def test_no_check_touches_the_network():
    module = _load()
    banned = {"curl", "wget", "http", "https", "ssh", "git"}
    for name, cmd in module.CHECKS:
        tokens = " ".join(cmd).lower().split()
        for token in banned:
            assert token not in tokens, (
                f"release_ready check {name!r} appears to touch the network: {cmd}"
            )
