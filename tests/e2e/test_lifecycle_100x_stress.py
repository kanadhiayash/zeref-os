"""H5.2: 100 consecutive fresh-project lifecycle repetitions.

Runs the prescribed lifecycle deterministic test 100 consecutive times
and asserts 100/100 successes. Reports:

  - attempts
  - successes
  - failures
  - first failing index (index of first non-success iteration)
  - duration summary (total, mean, max)

Marked ``slow`` so the fast pytest loop can skip it; the default
suite still runs it because pytest.ini addopts does not deselect it.

Implementation: repeatedly invoke the SAME test function inline (with
a fresh tmp_path each call) rather than spawning pytest subprocesses,
so the total wall clock stays under a minute on a modest laptop.
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest

from tests.e2e.test_fresh_project_lifecycle import test_fresh_project_lifecycle


REPETITIONS = 100


@pytest.mark.slow
def test_lifecycle_100_consecutive_repetitions(tmp_path: Path) -> None:
    attempts = 0
    successes = 0
    failures: list[tuple[int, str]] = []
    durations: list[float] = []

    for i in range(REPETITIONS):
        attempts += 1
        iter_dir = tmp_path / f"iter{i:03d}"
        iter_dir.mkdir()
        start = time.perf_counter()
        try:
            test_fresh_project_lifecycle(iter_dir)
        except Exception as exc:  # noqa: BLE001 -- capture every failure mode
            failures.append((i, f"{type(exc).__name__}: {exc}"))
        else:
            successes += 1
        durations.append(time.perf_counter() - start)

    first_failing_index = failures[0][0] if failures else None
    first_failing_reason = failures[0][1] if failures else None

    assert successes == REPETITIONS, (
        f"H5.2: {successes}/{REPETITIONS} lifecycle repetitions succeeded. "
        f"first failing index={first_failing_index}, reason={first_failing_reason}, "
        f"total_failures={len(failures)}, "
        f"duration_total={sum(durations):.2f}s, "
        f"duration_mean={statistics.fmean(durations):.3f}s, "
        f"duration_max={max(durations):.3f}s"
    )
