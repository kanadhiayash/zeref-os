from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_packages_are_absent():
    assert not (ROOT / "benchmarks").exists()
    assert not (ROOT / "shiroe/benchmark").exists()
    assert not (ROOT / "shiroe/cli_benchmark.py").exists()


def test_cli_has_no_benchmark_command():
    result = subprocess.run(
        [sys.executable, "-m", "shiroe", "--help"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "benchmark" not in result.stdout.lower()
