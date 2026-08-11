from __future__ import annotations

from shiroe.storage.state import StateDB


OBSOLETE = {
    "missions",
    "team_runs",
    "team_assignments",
    "execution_steps",
    "capability_benchmarks",
    "evaluator_runs",
    "codec_profiles",
}


def test_obsolete_runtime_tables_removed(tmp_path):
    with StateDB(tmp_path) as db:
        db.migrate()
        assert OBSOLETE.isdisjoint(set(db.tables()))
