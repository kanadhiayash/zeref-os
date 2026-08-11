import pytest

from shiroe.policy.approval_service import ApprovalService, AuthorizationError


def test_non_human_actor_cannot_approve(tmp_path):
    service = ApprovalService(tmp_path)
    req = service.request(
        approval_type="action",
        requested_action="publish",
        scope={"tag": "v1"},
        reason="public action",
        risk="high",
    )
    with pytest.raises(AuthorizationError, match="human"):
        service.decide_human(
            req.id,
            decision="approved",
            actor="approval-advisor",
            reason="looks good",
        )


def test_scope_change_makes_approval_stale(tmp_path):
    service = ApprovalService(tmp_path)
    req = service.request(
        approval_type="action",
        requested_action="publish",
        scope={"tag": "v1"},
        reason="public action",
        risk="high",
    )
    service.decide_human(req.id, decision="approved", actor="human", reason="approved")
    current = service.assert_current(req.id, current_scope={"tag": "v2"})
    assert current.status.value == "stale"
