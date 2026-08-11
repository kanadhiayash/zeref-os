# Phase 06: Approval Advisor and Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the one justified first-party reasoning agent, then make handoff reconstruct active work from canonical state without generic skill/codec/context layers.

**Architecture:** Approval Advisor is an operational Python service that invokes an approved reasoning capability and writes advice, never authorization. Handoff uses Work Graph, Memory, Approval and Verification state directly.

**Tech Stack:** capability adapter protocol, SQLite, JSON, Markdown, pytest.

## Global Constraints

- Approval Advisor cannot call the human decision write method.
- Advice and authorization are separate tables/events.
- Agent is active only when a healthy executable reasoning capability resolves.
- Handoff has JSON as canonical machine form and Markdown as human rendering.

---

### Task 1: Add approval advice state separate from approval decisions

**Files:**
- Create: `shiroe/migrations/m0005_approval_advice.py`
- Create: `shiroe/agents/__init__.py`
- Create: `shiroe/agents/approval_advisor.py`
- Test: `tests/unit/agents/test_approval_advisor.py`

**Interfaces:**
- Produces: `ApprovalAdvice`, `ApprovalAdvisor.advise(request_id, capability_id)`.

- [ ] **Step 1: Add advice table**

```sql
CREATE TABLE approval_advice (
    id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    rationale TEXT NOT NULL,
    risks_json TEXT NOT NULL,
    evidence_gaps_json TEXT NOT NULL,
    conditions_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(approval_id) REFERENCES approval_requests(id)
);
```

- [ ] **Step 2: Write privilege-separation tests with explicit helpers**

```python
from shiroe.policy.approval_service import ApprovalService


def _seed_pending_approval(root):
    return ApprovalService(root).request(
        approval_type="strategic",
        requested_action="choose release path",
        scope={"graph": "g1", "node": "approve-release"},
        reason="strategic boundary",
        risk="high",
        graph_id="g1",
        node_id=None,
    )


def test_advisor_writes_advice_not_authorization(tmp_path, executable_reasoning_capability):
    approval = _seed_pending_approval(tmp_path)
    advice = ApprovalAdvisor(tmp_path).advise(approval.id, executable_reasoning_capability.id)
    assert advice.recommendation in {"approve", "reject", "revise", "defer"}
    assert ApprovalService(tmp_path).get(approval.id).status.value == "pending"


def test_advisor_rejects_non_executable_reasoning_capability(tmp_path):
    approval = _seed_pending_approval(tmp_path)
    with pytest.raises(CapabilityGateError):
        ApprovalAdvisor(tmp_path).advise(approval.id, "context_only")
```

Define `executable_reasoning_capability` in the same test module using a tiny embedded adapter whose `invoke()` returns valid advisor JSON. Register it through CapabilityStore and the real adapter registry, exactly as Phase 04 registers the executable echo test adapter.

- [ ] **Step 3: Implement structured request payload**

Advisor input must contain:

```python
{
    "approval": approval_request_as_dict,
    "graph_context": upstream_and_downstream_node_summary,
    "verification": latest_verification_summary,
    "memory_decisions": relevant_active_decisions,
    "instruction": "Return JSON with recommendation, rationale, risks, evidence_gaps, conditions"
}
```

Validate returned JSON. Unknown recommendation blocks advice persistence. No code path imports or calls `decide_human()`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/agents/test_approval_advisor.py tests/invariant/test_human_approval_authority.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/agents shiroe/migrations/m0005_approval_advice.py tests/unit/agents
git commit -m "feat(approval): add non-authorizing advisor"
```

### Task 2: Implement independent semantic review as Verification mode, not Agent

**Files:**
- Create: `shiroe/verification/review.py`
- Modify: `shiroe/verification/engine.py`
- Test: `tests/unit/verification/test_independent_review.py`

**Interfaces:**
- Produces: `run_independent_review(..., capability_id) -> VerificationCheck`.

- [ ] **Step 1: Write independence test using one explicit capability id**

```python

def test_independent_review_rejects_executor_capability(tmp_path):
    capability_id = "test.reasoner"
    register_executable_reasoner(tmp_path, capability_id)
    with pytest.raises(ValueError, match="independent"):
        run_independent_review(tmp_path, node_id="n1", executor_capability_id=capability_id, reviewer_capability_id=capability_id)
```

Define `register_executable_reasoner(root, capability_id)` in the same test module using the real CapabilityStore/adapter registry path and an embedded adapter that returns a valid review JSON payload.

- [ ] **Step 2: Implement review verdict schema**

Allowed review verdicts: `pass`, `revise`, `block`. Map `revise` to Verification `warn` or `block` according to the node's required review policy; do not invent success.

- [ ] **Step 3: Run tests**

```bash
pytest tests/unit/verification/test_independent_review.py -q
```

- [ ] **Step 4: Commit**

```bash
git add shiroe/verification/review.py shiroe/verification/engine.py tests/unit/verification/test_independent_review.py
git commit -m "feat(verify): add capability-independent semantic review"
```

### Task 3: Rebuild handoff from canonical state

**Files:**
- Rewrite: `shiroe/handoff/compiler.py`
- Keep/refactor target renderers under `shiroe/handoff/`
- Create: `shiroe/handoff/schema.py`
- Test: `tests/integration/handoff/test_canonical_handoff.py`

**Interfaces:**
- Produces: `compile_handoff(root, *, graph_id, target) -> HandoffPacket`.

- [ ] **Step 1: Write canonical-state handoff test with local setup**

```python
from pathlib import Path
from shiroe.memory.models import MemoryWrite
from shiroe.memory.service import MemoryService
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


def _seed_active_graph_and_memory(root):
    graph = compile_work_graph({
        "id": "g-handoff",
        "objective": "continue elsewhere",
        "nodes": [{"id": "pending", "kind": "task", "objective": "next action", "requires": ["test.echo"]}],
        "edges": [],
    })
    WorkStore(root).create(graph)
    MemoryService(root).write(MemoryWrite(kind="decision", title="Handoff decision", claim="Keep work graph canonical", source_refs=("user-input",), privacy_class="internal", evidence_grade="C"))
    return graph.id


def _delete_generated_views(root):
    view_dir = Path(root) / "memory/views"
    if view_dir.exists():
        for path in view_dir.glob("*.md"):
            path.unlink()


def test_handoff_survives_deleted_markdown_views(tmp_path):
    graph_id = _seed_active_graph_and_memory(tmp_path)
    _delete_generated_views(tmp_path)
    packet = compile_handoff(tmp_path, graph_id=graph_id, target="human")
    assert packet.graph["id"] == graph_id
    assert packet.pending_nodes
    assert packet.active_decisions
```

- [ ] **Step 2: Define packet fields**

```python
@dataclass(frozen=True)
class HandoffPacket:
    schema: str
    graph: dict
    pending_nodes: tuple[dict, ...]
    pending_approvals: tuple[dict, ...]
    active_decisions: tuple[dict, ...]
    open_risks: tuple[dict, ...]
    verification: tuple[dict, ...]
    relevant_files: tuple[str, ...]
    next_actions: tuple[str, ...]
    generated_at: str
```

Canonical machine output is JSON. Markdown renderer may format the same packet, not re-query different sources.

- [ ] **Step 3: Update target renderers**

Claude/Codex/Cursor/human target modules may change formatting only. They may not drop pending approvals, decision provenance, verification blockers or graph id/version.

- [ ] **Step 4: Run tests**

```bash
pytest tests/integration/handoff/test_canonical_handoff.py -q
```

- [ ] **Step 5: Commit**

```bash
git add shiroe/handoff tests/integration/handoff
git commit -m "refactor(handoff): compile continuation from canonical graph state"
```

### Task 4: Remove generic context/codec abstractions not required by core

**Files:**
- Delete: `shiroe/context/`
- Delete generic codec registry/selector and unsupported formats under `shiroe/codecs/`
- Keep no generic codec package if handoff/memory can use stdlib JSON + direct Markdown rendering
- Delete codec/context-only tests after handoff tests cover surviving behavior
- Modify: `docs/architecture/REMOVALS.md`
- Test: `tests/invariant/test_no_generic_context_codec_surface.py`

- [ ] **Step 1: Write absence test**

```python
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_generic_context_and_codec_runtime_removed():
    assert not (ROOT / "shiroe/context").exists()
    assert not (ROOT / "shiroe/codecs").exists()
```

- [ ] **Step 2: Replace token estimation dependency before deletion**

Any remaining token estimate needed by Execution must live in `shiroe/execution/budget.py` as a local helper. Do not retain codec base solely for estimation.

- [ ] **Step 3: Delete and run tests**

```bash
pytest tests/integration/handoff tests/unit/agents tests/unit/verification/test_independent_review.py tests/invariant/test_no_generic_context_codec_surface.py -q
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(context): remove generic codec and packet layers"
```

## Phase gate

```bash
pytest tests/unit/agents tests/unit/verification tests/integration/handoff tests/invariant/test_human_approval_authority.py -q
```
