"""H6.1: canonical handoff continuity contract.

Compiling a handoff packet for every supported target from the same
canonical state must produce byte-identical values for the fields that
define continuation semantics -- because a downstream harness that
resumes from a divergent packet can silently execute a different plan
than the paused one.

Per the H6.1 handoff spec, the shared continuity fields are:

  - graph.id, graph.version, graph.status (same graph identity)
  - pending_nodes (dependency state)
  - pending_approvals (approval state)
  - active_decisions (decisions)
  - open_risks (evidence/risk state)
  - next_actions (next continuation point)

Fields intentionally allowed to differ per target: ``schema`` /
``generated_at`` / any private memory redaction. Those are excluded
from the contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from shiroe.handoff.compiler import TARGETS, compile_handoff
from shiroe.policy.approval_service import ApprovalService
from shiroe.work.compiler import compile_work_graph
from shiroe.work.store import WorkStore


CONTINUITY_FIELDS = (
    "pending_nodes",
    "pending_approvals",
    "active_decisions",
    "open_risks",
    "next_actions",
)


def _seed_state_with_pending_approval(root: Path) -> str:
    graph = compile_work_graph({
        "id": "g-cont",
        "objective": "test continuity contract",
        "nodes": [
            {"id": "approval", "kind": "approval",
             "objective": "gate", "approval_required": True,
             "metadata": {"scope": {"tag": "v1"}}},
            {"id": "task", "kind": "task",
             "objective": "publish", "requires": ["cap.publish"]},
        ],
        "edges": [{"from": "approval", "to": "task"}],
    })
    WorkStore(root).create(graph)
    ApprovalService(root).request(
        approval_type="strategic",
        requested_action="publish",
        scope={"tag": "v1"},
        reason="continuity test",
        risk="high",
        graph_id=graph.id,
        node_id="approval",
    )
    return graph.id


@pytest.fixture(scope="module")
def sorted_targets():
    return sorted(TARGETS)


def _packet_body(compile_result: dict) -> dict:
    """The canonical continuity packet lives under the ``packet`` key of
    compile_handoff's return value; ``target``/``markdown``/``json``/
    ``privacy``/``summary`` are per-target rendering metadata."""
    return compile_result["packet"]


def test_every_supported_target_agrees_on_continuity_fields(tmp_path, sorted_targets):
    graph_id = _seed_state_with_pending_approval(tmp_path)
    packets = {
        target: _packet_body(compile_handoff(tmp_path, target=target, graph_id=graph_id))
        for target in sorted_targets
    }
    baseline_target = sorted_targets[0]
    baseline = {f: packets[baseline_target].get(f) for f in CONTINUITY_FIELDS}
    for target in sorted_targets[1:]:
        for field in CONTINUITY_FIELDS:
            assert packets[target].get(field) == baseline[field], (
                f"H6.1: target {target!r} diverges from {baseline_target!r} on "
                f"continuity field {field!r}. "
                f"{baseline_target}={baseline[field]!r} vs {target}={packets[target].get(field)!r}"
            )


def test_graph_identity_is_identical_across_targets(tmp_path, sorted_targets):
    graph_id = _seed_state_with_pending_approval(tmp_path)
    graphs = {
        target: _packet_body(compile_handoff(tmp_path, target=target, graph_id=graph_id)).get("graph")
        for target in sorted_targets
    }
    baseline_target = sorted_targets[0]
    baseline = graphs[baseline_target]
    for target in sorted_targets[1:]:
        assert graphs[target] == baseline, (
            f"H6.1: target {target!r} reports a different graph than "
            f"{baseline_target!r}: {baseline!r} vs {graphs[target]!r}"
        )


def test_pending_approval_ids_are_stable_across_targets(tmp_path, sorted_targets):
    graph_id = _seed_state_with_pending_approval(tmp_path)
    approval_ids_by_target = {}
    for target in sorted_targets:
        body = _packet_body(compile_handoff(tmp_path, target=target, graph_id=graph_id))
        approvals = body.get("pending_approvals", ())
        approval_ids_by_target[target] = tuple(a.get("id") for a in approvals)
    ids = list(approval_ids_by_target.values())
    assert all(x == ids[0] for x in ids), (
        f"H6.1: pending_approvals ids diverge across targets: {approval_ids_by_target!r}"
    )
    assert ids[0], "expected at least one pending approval id in the packet"
