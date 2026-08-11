from shiroe.storage.state import StateDB


def test_approval_migration_creates_request_table(tmp_path):
    with StateDB(tmp_path) as db:
        db.migrate()
        tables = set(db.tables())
    assert "approval_requests" in tables
