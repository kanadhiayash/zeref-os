from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "shiroe-validate.py"

STALE_VALIDATOR_TERMS = (
    "PATTERNS.jsonl",
    "skill-route",
    "team-packs",
    "flat layout",
    "contract / experimental",
    "Auto-Activation",
)


def test_validator_source_is_vnext_positive() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for term in STALE_VALIDATOR_TERMS:
        assert term not in text


def test_validator_output_names_current_runtime_checks() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLI commands" in result.stdout
    assert "schema version" in result.stdout
    assert "default deny" in result.stdout
    assert "Validation passed" in result.stdout
