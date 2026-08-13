"""H1.1: exhaustive approval-state transition matrix.

Pins every allowed and forbidden transition of an ApprovalRequest so a
future change to ApprovalService cannot silently loosen or tighten the
contract. The matrix covers:

  1. pending -> {approved, rejected, revise, deferred} succeed
  2. decide_human rejects non-human actors
  3. decide_human refuses decision=pending / stale (not human decisions)
  4. Unknown approval id -> KeyError
  5. assert_current on same scope keeps status
  6. assert_current on different scope flips to stale
  7. scope_digest is deterministic across recreations
  8. decision persists decided_at / decided_by / decision_reason
  9. Re-decide (already-decided approval decided again) currently updates
     in place (pinned as observed behavior; see NOTE below).

NOTE for future hardening: (9) documents the current UPDATE-without-
from-status-guard behavior. Introducing a from-status check would be a
tightening; this test would then flip its assertion, and a fresh commit
would document the new invariant.
"""

from __future__ import annotations

import pytest

from shiroe.policy.approval_service import ApprovalService, AuthorizationError
from shiroe.policy.approvals import ApprovalStatus, scope_digest


def _request(root, *, request_id: str = "apr_h1", scope=None):
    return ApprovalService(root).request(
        approval_type="action",
        requested_action="do the thing",
        scope=scope or {"target": "x"},
        reason="matrix",
        risk="medium",
        request_id=request_id,
    )


@pytest.mark.parametrize(
    "decision",
    ["approved", "rejected", "revise", "deferred"],
)
def test_pending_transitions_to_every_human_decision(tmp_path, decision):
    req = _request(tmp_path, request_id=f"apr_{decision}")
    assert req.status is ApprovalStatus.pending
    updated = ApprovalService(tmp_path).decide_human(
        req.id, decision=decision, actor="human", reason="ok"
    )
    assert updated.status is ApprovalStatus(decision)


def test_decide_human_rejects_non_human_actor(tmp_path):
    req = _request(tmp_path)
    with pytest.raises(AuthorizationError):
        ApprovalService(tmp_path).decide_human(
            req.id, decision="approved", actor="agent", reason="nope"
        )


def test_decide_human_rejects_actor_kind_when_not_human(tmp_path):
    req = _request(tmp_path)
    with pytest.raises(AuthorizationError):
        ApprovalService(tmp_path).decide_human(
            req.id,
            decision="approved",
            actor="human",
            actor_kind="bot",
            reason="nope",
        )


@pytest.mark.parametrize("decision", ["pending", "stale"])
def test_decide_human_refuses_non_human_decisions(tmp_path, decision):
    req = _request(tmp_path)
    with pytest.raises(ValueError):
        ApprovalService(tmp_path).decide_human(
            req.id, decision=decision, actor="human", reason="nope"
        )


def test_decide_human_unknown_id_raises_key_error(tmp_path):
    _request(tmp_path)
    with pytest.raises(KeyError):
        ApprovalService(tmp_path).decide_human(
            "apr_missing", decision="approved", actor="human", reason="?"
        )


def test_assert_current_same_scope_preserves_status(tmp_path):
    req = _request(tmp_path, scope={"tag": "v1"})
    same = ApprovalService(tmp_path).assert_current(req.id, current_scope={"tag": "v1"})
    assert same.status is ApprovalStatus.pending


def test_assert_current_scope_change_marks_stale(tmp_path):
    req = _request(tmp_path, scope={"tag": "v1"})
    ApprovalService(tmp_path).decide_human(
        req.id, decision="approved", actor="human", reason="fine"
    )
    stale = ApprovalService(tmp_path).assert_current(
        req.id, current_scope={"tag": "v2"}
    )
    assert stale.status is ApprovalStatus.stale


def test_scope_digest_is_deterministic():
    a = scope_digest({"a": 1, "b": 2})
    b = scope_digest({"b": 2, "a": 1})
    assert a == b
    assert a.startswith("sha256:")


def test_decision_persists_actor_reason_and_timestamp(tmp_path):
    req = _request(tmp_path)
    updated = ApprovalService(tmp_path).decide_human(
        req.id, decision="approved", actor="human", reason="LGTM"
    )
    assert updated.decided_by == "human"
    assert updated.decision_reason == "LGTM"
    assert updated.decided_at  # non-empty ISO timestamp


def test_redecide_currently_overwrites_in_place(tmp_path):
    """Pin observed behavior: no from-status guard, so re-deciding wins.

    This test will flip to a raises() assertion if a future change adds a
    from-status guard. That is the correct place to document the
    hardening.
    """
    svc = ApprovalService(tmp_path)
    req = _request(tmp_path)
    svc.decide_human(req.id, decision="approved", actor="human", reason="first")
    again = svc.decide_human(
        req.id, decision="rejected", actor="human", reason="changed my mind"
    )
    assert again.status is ApprovalStatus.rejected
    assert again.decision_reason == "changed my mind"
