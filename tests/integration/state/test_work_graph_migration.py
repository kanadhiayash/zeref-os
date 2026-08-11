from shiroe.storage.state import StateDB


def test_work_graph_migration_creates_required_tables(tmp_path):
    with StateDB(tmp_path) as db:
        db.migrate()
        tables = set(db.tables())
    assert {"work_graphs", "work_nodes", "work_edges", "work_attempts"} <= tables
