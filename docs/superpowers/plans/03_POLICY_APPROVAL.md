# Phase 03: Policy and Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make human approvals first-class, persisted, scope-bound runtime state integrated with policy and Work Graph readiness.

**Architecture:** `policy.evaluate()` stays pure. `ApprovalService` creates and decides approval records. Authorization is granted only through explicit human decision calls. Agent advice is added later and cannot write decisions.

**Tech Stack:** dataclasses, enums, SQLite, SHA-256, canonical JSON, pytest.

## Global Constraints

- Existing policy precedence remains authoritative.
- `ALWAYS_REQUIRE_APPROVAL` actions remain non-bypassable.
- Approval scope changes invalidate the old approval.
- Agent/model output cannot write `approved` state.

---

### Task 1: Add approval domain and state tables

**Files:**
- Create: `shiroe/policy/approvals.py`
- Create: `shiroe/migrations/m0004_approvals.py`
- Test: `tests/unit/policy/test_approvals.py`
- Test: `tests/integration/state/test_approval_migration.py`

**Interfaces:**
- Produces: `ApprovalType`, `ApprovalStatus`, `ApprovalRequest`, `ApprovalDecision`, `scope_digest(payload)`.

- [ ] **Step 1: Write failing digest/status tests**

```python
from shiroe.policy.approvals import ApprovalStatus, scope_digest


def test_scope_digest_is_order_independent_for_dict_keys():
    assert scope_digest({"b": 2, "a": 1}) == scope_digest({"a": 1, "b": 2})


def test_scope_digest_changes_when_scope_changes():
    assert scope_digest({"files": ["a"]}) != scope_digest({"files": ["a", "b"]})


def test_approved_status_is_not_default():
    assert ApprovalStatus.pending.value == "pending"
```

- [ ] **Step 2: Implement canonical digest**

```python
def scope_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
```

Approval types: `action`, `strategic`, `exception`. Statuses: `pending`, `approved`, `rejected`, `revise`, `deferred`, `stale`.

- [ ] **Step 3: Add tables**

```sql
CREATE TABLE approval_requests (
    id TEXT PRIMARY KEY,
    graph_id TEXT,
    node_id TEXT,
    approval_type TEXT NOT NULL,
    action_kind TEXT,
    requested_action TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    scope_digest TEXT NOT NULL,
    reason TEXT NOT NULL,
    options_json TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    risk TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    decision_reason TEXT,
    FOREIGN KEY(graph_id) REFERENCES work_graphs(id),
    FOREIGN KEY(node_id) REFERENCES work_nodes(id)
);
CREATE INDEX ix_approval_status ON approval_requests(status);
CREATE INDEX ix_approval_graph ON approval_requests(graph_id);
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/policy/test_approvals.py tests/integration/state/test_approval_migration.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/policy/approvals.py shiroe/migrations/m0004_approvals.py tests/unit/policy tests/integration/state/test_approval_migration.py
git commit -m "feat(policy): persist scope-bound approvals"
```

### Task 2: Implement ApprovalService with human-only decision API

**Files:**
- Create: `shiroe/policy/approval_service.py`
- Test: `tests/invariant/test_human_approval_authority.py`

**Interfaces:**
- Produces: `ApprovalService.request(...)`, `ApprovalService.decide_human(...)`, `ApprovalService.get(...)`, `ApprovalService.assert_current(...)`.

- [ ] **Step 1: Write authority tests**

```python
import pytest
from shiroe.policy.approval_service import ApprovalService, AuthorizationError


def test_non_human_actor_cannot_approve(tmp_path):
    service = ApprovalService(tmp_path)
    req = service.request(approval_type="action", requested_action="publish", scope={"tag": "v1"}, reason="public action", risk="high")
    with pytest.raises(AuthorizationError, match="human"):
        service.decide_human(req.id, decision="approved", actor="approval-advisor", reason="looks good")


def test_scope_change_makes_approval_stale(tmp_path):
    service = ApprovalService(tmp_path)
    req = service.request(approval_type="action", requested_action="publish", scope={"tag": "v1"}, reason="public action", risk="high")
    service.decide_human(req.id, decision="approved", actor="human", reason="approved")
    current = service.assert_current(req.id, current_scope={"tag": "v2"})
    assert current.status.value == "stale"
```

- [ ] **Step 2: Prove failure**

```bash
pytest tests/invariant/test_human_approval_authority.py -q
```

- [ ] **Step 3: Implement service**

`decide_human()` must accept only actor exactly `human` or an explicit human identity passed by the CLI layer with `actor_kind="human"`. It must reject agent/capability actors. It writes `decided_at`, `decided_by`, `decision_reason` in one transaction.

`assert_current()` recomputes digest; if it differs, update status to `stale` and return the stale request.

- [ ] **Step 4: Run tests**

```bash
pytest tests/invariant/test_human_approval_authority.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/policy/approval_service.py tests/invariant/test_human_approval_authority.py
git commit -m "feat(policy): enforce human-only approval authority"
```

### Task 3: Integrate policy `require_approval` with approval creation

**Files:**
- Create: `shiroe/policy/service.py`
- Modify: `shiroe/policy/__init__.py`
- Test: `tests/integration/policy/test_authorization_flow.py`
- Preserve/rehome: `tests/test_policy_export_gates.py`

**Interfaces:**
- Produces: `PolicyService.authorize(action, *, graph_id=None, node_id=None, scope=None, mode=...) -> AuthorizationResult`.

- [ ] **Step 1: Write flow tests**

```python

def test_publish_creates_pending_approval(tmp_path):
    result = PolicyService(tmp_path).authorize(Action(ActionKind.publish, target="v1"), scope={"tag": "v1"})
    assert result.verdict.value == "require_approval"
    assert result.approval_id


def test_project_deny_does_not_create_approval(tmp_path):
    result = PolicyService.with_project_deny(tmp_path, ActionKind.publish).authorize(Action(ActionKind.publish, target="v1"), scope={"tag": "v1"})
    assert result.verdict.value == "deny"
    assert result.approval_id is None
```

- [ ] **Step 2: Implement service without changing pure `evaluate()`**

```python
@dataclass(frozen=True)
class AuthorizationResult:
    verdict: Verdict
    reason: str
    deciding_layer: str
    approval_id: str | None = None
```

If `evaluate()` returns `require_approval`, create/reuse a pending request for the same graph/node/action/scope digest. If it returns deny, never create an approval request.

- [ ] **Step 3: Port policy precedence adversarial tests unchanged in meaning**

The existing permutations proving lower-precedence allows cannot widen project/global denies must still pass. Existing attempts to bypass `ALWAYS_REQUIRE_APPROVAL` through `Action.context` must still land `require_approval`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/integration/policy/test_authorization_flow.py tests/test_policy_export_gates.py tests/test_vnext_pr3_policy.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/policy tests/integration/policy tests/test_policy_export_gates.py tests/test_vnext_pr3_policy.py
git commit -m "feat(policy): turn approval verdicts into runtime requests"
```

### Task 4: Integrate approval nodes with Work Graph readiness

**Files:**
- Modify: `shiroe/work/readiness.py`
- Modify: `shiroe/work/store.py`
- Test: `tests/integration/work/test_approval_nodes.py`

**Interfaces:**
- Consumes: `ApprovalService`.
- Produces: approval node completes only from approved current request.

- [ ] **Step 1: Write graph tests with local helpers**

```python
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


def _seed_graph_with_approval(root):
    graph = compile_work_graph({
        "id": "g-approval",
        "objective": "publish",
        "nodes": [
            {"id": "approval", "kind": "approval", "objective": "Approve publish", "approval_required": True, "metadata": {"scope": {"tag": "v1"}}},
            {"id": "after", "kind": "task", "objective": "Publish", "requires": ["test.publish"]},
        ],
        "edges": [{"from": "approval", "to": "after"}],
    })
    WorkStore(root).create(graph)
    request = ApprovalService(root).request(
        approval_type="strategic",
        requested_action="publish v1",
        scope={"tag": "v1"},
        reason="graph approval node",
        risk="high",
        graph_id=graph.id,
        node_id="approval",
    )
    return graph.id, request.id


def test_downstream_node_waits_for_approved_current_scope(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    store = WorkStore(tmp_path)
    assert store.ready_node_ids(graph_id) == ("approval",)
    ApprovalService(tmp_path).decide_human(approval_id, decision="approved", actor="human", reason="approved")
    store.refresh_readiness(graph_id)
    assert "after" in store.ready_node_ids(graph_id)


def test_stale_approval_reblocks_downstream_node(tmp_path):
    graph_id, approval_id = _seed_graph_with_approval(tmp_path)
    service = ApprovalService(tmp_path)
    service.decide_human(approval_id, decision="approved", actor="human", reason="approved")
    service.assert_current(approval_id, current_scope={"tag": "v2"})
    WorkStore(tmp_path).refresh_readiness(graph_id)
    assert "after" not in WorkStore(tmp_path).ready_node_ids(graph_id)
```

- [ ] **Step 2: Implement readiness check**

Approval nodes are treated as completed only when `ApprovalService.assert_current()` returns `approved` for the exact current node scope digest.

- [ ] **Step 3: Run tests**

```bash
pytest tests/integration/work/test_approval_nodes.py tests/unit/work/test_readiness.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/work tests/integration/work/test_approval_nodes.py
git commit -m "feat(work): gate graph progress on current approval"
```

## Phase gate

```bash
pytest tests/unit/policy tests/integration/policy tests/integration/work/test_approval_nodes.py tests/invariant/test_human_approval_authority.py tests/test_policy_export_gates.py -q
```
