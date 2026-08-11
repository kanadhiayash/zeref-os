from shiroe.policy import Action, ActionKind, AutonomyMode, Verdict, evaluate
from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.schema import PolicyLayer
from shiroe.policy.service import PolicyService


def test_existing_human_approval_cannot_override_project_deny(tmp_path):
    approval = ApprovalService(tmp_path).request(
        approval_type="action",
        requested_action="release",
        action_kind=ActionKind.publish.value,
        scope={"tag": "v1"},
        reason="release",
        risk="high",
    )
    ApprovalService(tmp_path).decide_human(
        approval.id,
        decision="approved",
        actor="human",
        reason="approved earlier",
    )

    result = PolicyService.with_project_deny(tmp_path, ActionKind.publish).authorize(
        Action(ActionKind.publish, target="release"),
        scope={"tag": "v1"},
    )

    assert result.verdict is Verdict.deny
    assert result.approval_id is None


def test_lower_layer_grant_cannot_override_higher_default_deny():
    decision = evaluate(
        Action(ActionKind.fs_write, target="memory/hot.md"),
        [
            PolicyLayer(name="project-defaults", denies=frozenset({ActionKind.fs_write})),
            PolicyLayer(name="global-defaults", allows=frozenset({ActionKind.fs_write})),
            PolicyLayer(name="harness-defaults", allows=frozenset({ActionKind.fs_write})),
        ],
        mode=AutonomyMode.policy_bound,
    )

    assert decision.verdict is Verdict.deny
    assert decision.deciding_layer == "project-defaults"
