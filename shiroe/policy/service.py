"""Runtime policy service that turns approval verdicts into approval requests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from shiroe.policy.approval_service import ApprovalService
from shiroe.policy.autonomy import AutonomyMode
from shiroe.policy.engine import evaluate
from shiroe.policy.loader import load_policy_stack
from shiroe.policy.schema import Action, ActionKind, PolicyLayer, Verdict


@dataclass(frozen=True)
class AuthorizationResult:
    verdict: Verdict
    reason: str
    deciding_layer: str
    approval_id: str | None = None


class PolicyService:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.approvals = ApprovalService(self.root)

    @classmethod
    def with_project_deny(cls, root: Path | str, kind: ActionKind) -> "PolicyService":
        root_path = Path(root)
        policy_dir = root_path / ".shiroe" / "policy"
        policy_dir.mkdir(parents=True, exist_ok=True)
        (policy_dir / "deny.json").write_text(
            json.dumps({"deny": [kind.value]}, sort_keys=True),
            encoding="utf-8",
        )
        return cls(root_path)

    def _stack_for(self, action: Action) -> list[PolicyLayer]:
        stack = load_policy_stack(self.root, global_root=self.root / "no-global-policy")
        # Service-level authorization represents an explicit attempt to perform
        # the action. This grant lets pure policy reach the autonomy gate while
        # project/global denies still win by precedence.
        stack.append(
            PolicyLayer(
                name="explicit-user-grant",
                allows=frozenset({action.kind}),
            )
        )
        return stack

    def authorize(
        self,
        action: Action,
        *,
        graph_id: str | None = None,
        node_id: str | None = None,
        scope: Mapping[str, Any] | None = None,
        mode: AutonomyMode = AutonomyMode.policy_bound,
    ) -> AuthorizationResult:
        decision = evaluate(action, self._stack_for(action), mode=mode)
        if decision.verdict is not Verdict.require_approval:
            return AuthorizationResult(
                verdict=decision.verdict,
                reason=decision.reason,
                deciding_layer=decision.deciding_layer,
            )

        current_scope = dict(scope or {"target": action.target, "context": action.context or {}})
        requested_action = action.target or action.kind.value
        existing = self.approvals.find_pending(
            graph_id=graph_id,
            node_id=node_id,
            action_kind=action.kind.value,
            requested_action=requested_action,
            scope=current_scope,
        )
        req = existing or self.approvals.request(
            approval_type="action",
            requested_action=requested_action,
            scope=current_scope,
            reason=decision.reason,
            risk="high" if action.kind in {
                ActionKind.publish,
                ActionKind.push,
                ActionKind.merge,
                ActionKind.destructive,
                ActionKind.fs_delete,
            } else "medium",
            graph_id=graph_id,
            node_id=node_id,
            action_kind=action.kind.value,
        )
        return AuthorizationResult(
            verdict=decision.verdict,
            reason=decision.reason,
            deciding_layer=decision.deciding_layer,
            approval_id=req.id,
        )
