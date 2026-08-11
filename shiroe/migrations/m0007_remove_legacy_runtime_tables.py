"""m0007 — remove obsolete pre-vNext runtime tables after backup."""

from __future__ import annotations

import sqlite3


DESTRUCTIVE = True


def up(conn: sqlite3.Connection) -> None:
    for table in (
        "team_assignments",
        "execution_steps",
        "team_runs",
        "missions",
        "capability_benchmarks",
        "evaluator_runs",
        "codec_profiles",
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
