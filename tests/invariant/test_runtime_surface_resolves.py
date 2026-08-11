import importlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_runtime_components_import():
    for module in (
        "shiroe.storage",
        "shiroe.policy",
        "shiroe.capabilities",
        "shiroe.memory",
        "shiroe.handoff",
        "shiroe.release",
    ):
        importlib.import_module(module)


def test_cli_commands_resolve_without_contract_registry():
    result = subprocess.run(
        [sys.executable, "-m", "shiroe", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    help_text = result.stdout
    for command in ("init", "status", "memory", "handoff", "doctor", "policy", "capability", "state", "version"):
        assert command in help_text
    for removed in ("benchmark", "skills/drafts", "team-packs"):
        assert removed not in help_text
