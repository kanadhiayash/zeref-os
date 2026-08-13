"""H1.2: approval requests survive service close/reopen cycles.

A pause/resume roundtrip in production spans multiple ApprovalService
instances -- the supervisor opens one on run(), a CLI opens another on
"shiroe approve decide", the supervisor opens a third on resume(). If
any of those instances lost data across close/reopen, the H0.2 fix
would only work in-process. These tests pin durability across three
open/close cycles for both pending and decided requests, plus a
scope-digest check across a decide/reopen cycle.
"""

from __future__ import annotations

from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.approvals import ApprovalStatus, scope_digest


def _seed(root, request_id="apr_p1"):
    svc = ApprovalService(root)
    req = svc.request(
        approval_type="action",
        requested_action="publish",
        scope={"target": "v1"},
        reason="persistence",
        risk="medium",
        request_id=request_id,
    )
    svc.close()
    return req


def _reopen_get(root, approval_id):
    svc = ApprovalService(root)
    try:
        return svc.get(approval_id)
    finally:
        svc.close()


def test_pending_request_survives_three_reopen_cycles(tmp_path):
    seeded = _seed(tmp_path)
    for _ in range(3):
        read = _reopen_get(tmp_path, seeded.id)
        assert read.id == seeded.id
        assert read.status is ApprovalStatus.pending
        assert read.digest == seeded.digest


def test_decided_request_survives_three_reopen_cycles(tmp_path):
    seeded = _seed(tmp_path, request_id="apr_p2")

    svc = ApprovalService(tmp_path)
    svc.decide_human(seeded.id, decision="approved", actor="human", reason="fine")
    svc.close()

    for _ in range(3):
        read = _reopen_get(tmp_path, seeded.id)
        assert read.status is ApprovalStatus.approved
        assert read.decision_reason == "fine"
        assert read.decided_by == "human"
        assert read.decided_at


def test_find_latest_matching_locates_row_after_reopen(tmp_path):
    _seed(tmp_path, request_id="apr_p3")

    svc = ApprovalService(tmp_path)
    try:
        hit = svc.find_latest_matching(
            graph_id=None,
            node_id=None,
            action_kind=None,
            requested_action="publish",
            scope={"target": "v1"},
        )
    finally:
        svc.close()
    assert hit is not None
    assert hit.id == "apr_p3"
    assert hit.digest == scope_digest({"target": "v1"})


def test_scope_digest_is_stable_across_reopen(tmp_path):
    seeded = _seed(tmp_path, request_id="apr_p4")

    for _ in range(3):
        read = _reopen_get(tmp_path, seeded.id)
        assert read.digest == scope_digest({"target": "v1"})
