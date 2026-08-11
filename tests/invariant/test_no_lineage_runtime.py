from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_lineage_runtime_is_absent():
    assert not (ROOT / "shiroe/lineage").exists()
    help_text = subprocess.run(
        [sys.executable, "-m", "shiroe", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    assert "lineage" not in help_text
