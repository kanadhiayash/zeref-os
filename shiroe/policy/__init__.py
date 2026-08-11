"""Policy & permission engine (vNext §13.3, ADR-0005).

Central decision surface. Every call site that could touch the filesystem
outside allowed scopes, hit the network, read secrets, spawn a subprocess,
write outside the project, or take a destructive action must call
:func:`shiroe.policy.evaluate` first.

The chain (highest wins; lower may only *narrow* a higher grant, never
widen a higher deny):

    1. Runtime safety invariants (hardcoded, never negotiable)
    2. Project deny rules  (.shiroe/policy/deny.json OR config/PERMISSIONS.md)
    3. Global deny rules   (~/.shiroe/policies/deny.json)
    4. Explicit user grants (per-session, in-memory)
    5. Project defaults    (config/PERMISSIONS.md)
    6. Global defaults     (~/.shiroe/policies/defaults.json)
    7. Harness defaults    (adapter-supplied)
"""

from shiroe.policy.schema import Action, ActionKind, Decision, Verdict
from shiroe.policy.approvals import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    scope_digest,
)
from shiroe.policy.approval_service import ApprovalService, AuthorizationError
from shiroe.policy.autonomy import (
    ALWAYS_REQUIRE_APPROVAL,
    AutonomyMode,
    autonomy_gate,
)
from shiroe.policy.engine import evaluate
from shiroe.policy.loader import load_policy_stack

__all__ = [
    "Action", "ActionKind", "Decision", "Verdict",
    "ApprovalDecision", "ApprovalRequest", "ApprovalStatus", "ApprovalType",
    "ApprovalService", "AuthorizationError", "scope_digest",
    "ALWAYS_REQUIRE_APPROVAL", "AutonomyMode", "autonomy_gate",
    "evaluate", "load_policy_stack",
]
