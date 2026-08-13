"""H2.3: pin context-manager contract on the SQLite-backed stores.

Every long-lived store that owns a sqlite3 connection must be usable as
a context manager so callers can guarantee cleanup without paying
attention to explicit close(). Regression coverage: an unclosed store
leaks a file handle to memory/state/shiroe.sqlite -- fine on macOS in
tests, but a real issue for long-running processes and for platforms
with tighter fd limits.
"""

from __future__ import annotations

from shiroe.capabilities.store import CapabilityStore
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.store import WorkStore


def test_work_store_supports_with_statement(tmp_path):
    with WorkStore(tmp_path) as store:
        assert store.conn is not None


def test_capability_store_supports_with_statement(tmp_path):
    with CapabilityStore(tmp_path) as store:
        assert store.conn is not None


def test_approval_service_supports_with_statement(tmp_path):
    with ApprovalService(tmp_path) as svc:
        assert svc.conn is not None


def test_with_statement_closes_underlying_db(tmp_path):
    with ApprovalService(tmp_path) as svc:
        db = svc.db
    assert db._conn is None


def test_close_is_idempotent_on_all_three_stores(tmp_path):
    for factory in (WorkStore, CapabilityStore, ApprovalService):
        s = factory(tmp_path)
        s.close()
        s.close()


def test_context_manager_exits_cleanly_on_exception(tmp_path):
    class _Boom(RuntimeError):
        pass

    try:
        with ApprovalService(tmp_path) as svc:
            db = svc.db
            raise _Boom()
    except _Boom:
        pass
    assert db._conn is None
