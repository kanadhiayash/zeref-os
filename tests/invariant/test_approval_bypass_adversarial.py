import pytest

from shiroe.policy.approval_service import ApprovalService, AuthorizationError


def test_actor_kind_cannot_spoof_human_approval_authority(tmp_path):
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
            actor_kind="human",
            reason="spoofed human role",
        )

    assert service.get(req.id).status.value == "pending"


def test_approval_for_one_scope_cannot_authorize_mutated_scope(tmp_path):
    service = ApprovalService(tmp_path)
    req = service.request(
        approval_type="action",
        requested_action="publish",
        scope={"tag": "v1", "files": ["dist/app.js"]},
        reason="public action",
        risk="high",
    )
    service.decide_human(req.id, decision="approved", actor="human", reason="approved")

    current = service.assert_current(
        req.id,
        current_scope={"tag": "v1", "files": ["dist/app.js", "dist/secrets.json"]},
    )

    assert current.status.value == "stale"
