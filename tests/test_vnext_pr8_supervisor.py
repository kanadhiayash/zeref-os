"""vNext PR 8 gate tests — runtime supervisor."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.capabilities import (
    approve,
    inspect_source,
    register_discovery,
)
from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import AutonomyMode
from shiroe.runtime import (
    BudgetTracker,
    Supervisor,
    can_run_transition,
    can_step_transition,
    resume,
)
from shiroe.runtime.state_machine import (
    IRREVERSIBLE_TERMINAL_STEP_STATES,
    RUN_STATES,
    STEP_STATES,
    assert_run_transition,
    assert_step_transition,
    INVALID_RUN_TRANSITION,
    INVALID_STEP_TRANSITION,
)
from shiroe.storage import EventLog
from shiroe.teams import compile_team

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# State machines
# ---------------------------------------------------------------------------

def test_run_state_set_matches_spec() -> None:
    for s in ("CREATED", "COMPILED", "AUTHORIZED", "RUNNING", "VERIFYING",
              "COMPLETED", "PAUSED_PERMISSION", "PAUSED_BUDGET", "RETRYING",
              "DEGRADED", "FAILED", "CANCELLED"):
        assert s in RUN_STATES


def test_step_state_set_matches_spec() -> None:
    for s in ("PENDING", "READY", "RUNNING", "OUTPUT_RECEIVED", "VALIDATING",
              "PASSED", "TIMED_OUT", "RETRYABLE_FAILURE", "PERMISSION_DENIED",
              "INVALID_OUTPUT", "FAILED", "SKIPPED"):
        assert s in STEP_STATES


def test_run_transitions_reject_illegal() -> None:
    with pytest.raises(INVALID_RUN_TRANSITION):
        assert_run_transition("COMPLETED", "RUNNING")
    with pytest.raises(INVALID_RUN_TRANSITION):
        assert_run_transition("CREATED", "COMPLETED")
    assert can_run_transition("RUNNING", "VERIFYING")


def test_step_transitions_reject_illegal() -> None:
    with pytest.raises(INVALID_STEP_TRANSITION):
        assert_step_transition("PASSED", "RUNNING")
    with pytest.raises(INVALID_STEP_TRANSITION):
        assert_step_transition("PENDING", "PASSED")
    assert can_step_transition("VALIDATING", "PASSED")


def test_irreversible_terminal_step_states_defined() -> None:
    assert IRREVERSIBLE_TERMINAL_STEP_STATES == {"PASSED", "SKIPPED"}


# ---------------------------------------------------------------------------
# Budget tracker
# ---------------------------------------------------------------------------

def test_budget_tracker_flags_exceeded() -> None:
    b = BudgetTracker(usd_max=1.0, tokens_input_max=1000, tokens_output_max=1000)
    b.charge(usd=0.5, tokens_input=100, tokens_output=100)
    assert b.exceeded() is None
    b.charge(usd=0.6)
    assert "usd_max" in (b.exceeded() or "")


# ---------------------------------------------------------------------------
# End-to-end fixture
# ---------------------------------------------------------------------------

def _seed(tmp_path: Path) -> str:
    """Compile a real build-mission run in an isolated workspace and
    return the run_id."""
    for name in ("missions", "policies"):
        shutil.copytree(REPO_ROOT / name, tmp_path / name)

    # Allow subprocess actions so the sample capability adapter doesn't
    # bounce; the fake invoker below never actually spawns anything.
    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess", "memory.write"]}),
        encoding="utf-8",
    )

    for name, provides in (
        ("architect", ["architecture-planning", "dependency-analysis"]),
        ("coder", ["code-editing", "test-execution"]),
        ("reviewer", ["code-review", "verification"]),
    ):
        src = tmp_path / "source" / name
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        d = DiscoveredCapability(
            adapter="generic", root="<home>/skills", path=src, kind="skill",
        )
        cid = register_discovery(tmp_path, d, trust=inspect_source(src))
        # inject provides into manifest
        store = CapabilityStore(tmp_path)
        try:
            row = store.conn.execute(
                "SELECT id, manifest FROM capability_versions "
                "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
                (cid,),
            ).fetchone()
            manifest = json.loads(row[1])
            manifest["provides"] = provides
            store.conn.execute(
                "UPDATE capability_versions SET manifest=? WHERE id=?",
                (json.dumps(manifest, sort_keys=True), row[0]),
            )
            store.conn.commit()
        finally:
            store.close()
        approve(tmp_path, cid)

    plan = compile_team(tmp_path, task_id="task_e2e", mission_id="build",
                        policy_id="balanced", active_harness="claude-code")
    return plan.run_id


def _ok_invoker(step_id: str, step_name: str, cap_id: str, ctx: dict) -> AdapterResult:
    return AdapterResult(ok=True, output=f"done:{step_name}",
                         exit_code=0, metadata={"enforcement_level": "A"})


def _fail_once():
    calls: dict = {"n": 0}
    def _inv(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            return AdapterResult(ok=False, error="transient boom")
        return AdapterResult(ok=True, output="ok")
    return _inv


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_happy_path_run_completes(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"
    assert result.completed_steps == ["planner", "implementer", "verifier"]


def test_happy_path_events_hash_chain_valid(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker)
    try:
        sup.run()
    finally:
        sup.close()
    log = EventLog(tmp_path)
    log.verify_chain()
    types = {e["event_type"] for e in log.iter_events()}
    for required in ("run.authorized", "run.started", "run.completed",
                     "step.started", "step.completed"):
        assert required in types


# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------

def test_transient_failure_retried_and_succeeds(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)
    invoker = _fail_once()
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=invoker)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"


# ---------------------------------------------------------------------------
# Recovery / resume — PR 8 gate
# ---------------------------------------------------------------------------

def _stop_after_first(step_count: dict):
    def _inv(step_id, step_name, cap_id, ctx):
        step_count["n"] += 1
        if step_count["n"] == 1:
            return AdapterResult(ok=True, output="first-ok")
        # Simulate an unrecoverable error so we can stop mid-run.
        raise KeyboardInterrupt("interrupted")
    return _inv


def test_resume_never_reruns_completed_irreversible_step(tmp_path: Path) -> None:
    """The PR-8 acceptance gate: after a mid-run interruption, resume picks
    up at the FIRST non-PASSED/SKIPPED step. Completed steps do NOT re-run."""
    run_id = _seed(tmp_path)

    counter = {"n": 0}
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_stop_after_first(counter))
    with pytest.raises(KeyboardInterrupt):
        sup.run()
    sup.close()

    # exactly one step PASSED on the first attempt
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        passed_1 = conn.execute(
            "SELECT step_name FROM execution_steps "
            "WHERE run_id=? AND state='PASSED' ORDER BY id",
            (run_id,),
        ).fetchall()
    finally:
        conn.close()
    assert len(passed_1) == 1

    # Resume with an invoker that COUNTS invocations. First step must not
    # re-invoke; only the remaining two do.
    resume_counter = {"n": 0, "seen": []}
    def _resume_invoker(step_id, step_name, cap_id, ctx):
        resume_counter["n"] += 1
        resume_counter["seen"].append(step_name)
        return AdapterResult(ok=True, output="resume-ok")

    # The interrupted supervisor left the run in RUNNING; the resume
    # supervisor picks it up as-is.
    result = resume(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                    invoker=_resume_invoker)
    assert result.state == "COMPLETED"
    # exactly two steps ran on resume — the first completed step was not
    # re-invoked (the acceptance gate).
    assert resume_counter["n"] == 2
    assert passed_1[0][0] not in resume_counter["seen"]


# ---------------------------------------------------------------------------
# Capability revocation mid-run — no silent substitution
# ---------------------------------------------------------------------------

def test_pre_revoked_capability_pauses_permission(tmp_path: Path) -> None:
    """Pre-revoke a capability the plan depends on; supervisor's
    per-step assert_executable trips and the run pauses with the
    specific PAUSED_PERMISSION state (not a generic post-retry FAILED).

    Mid-run revocation from a live in-process session is covered by
    test_capability_lifecycle_registry.py.
    """
    run_id = _seed(tmp_path)
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT capability_id FROM team_assignments "
            "WHERE run_id=? AND seat_id='planner'", (run_id,),
        ).fetchone()
    finally:
        conn.close()
    victim = row[0]
    from shiroe.capabilities import revoke
    revoke(tmp_path, victim)

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "PAUSED_PERMISSION"
    assert "capability gate" in (result.paused_reason or "").lower()
