import json

from shiroe.policy.schema import Action, ActionKind
from shiroe.policy.service import PolicyService


def test_publish_creates_pending_approval(tmp_path):
    policy_dir = tmp_path / ".shiroe" / "policy"
    policy_dir.mkdir(parents=True)
    (policy_dir / "defaults.json").write_text(
        json.dumps({"allow": [ActionKind.publish.value]}),
        encoding="utf-8",
    )

    result = PolicyService(tmp_path).authorize(
        Action(ActionKind.publish, target="v1"),
        scope={"tag": "v1"},
    )
    assert result.verdict.value == "require_approval"
    assert result.approval_id


def test_project_deny_does_not_create_approval(tmp_path):
    result = PolicyService.with_project_deny(tmp_path, ActionKind.publish).authorize(
        Action(ActionKind.publish, target="v1"),
        scope={"tag": "v1"},
    )
    assert result.verdict.value == "deny"
    assert result.approval_id is None
