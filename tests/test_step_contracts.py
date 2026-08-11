"""Per-step contract tests (PR14 — SHR-055/056/057/058/063).

Every step invocation now has a bounded outcome: usage aggregated into
``BudgetTracker``, malformed output → deterministic FAILED, timeout →
deterministic FAILED with reason=timeout, retry exhaustion → FAILED with
reason=retry_exhausted, and per-step budget projection → PAUSED_BUDGET
before invocation. Resume across a pause reproduces the same usage
totals as a control run.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.capabilities import approve, inspect_source, register_discovery
from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import AutonomyMode
from shiroe.runtime import Supervisor, resume

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixture — a real compiled run, patched with per-step contract fields
# ---------------------------------------------------------------------------

BUILD_MISSION_STEPS = ("planner", "implementer", "verifier")


def _write_build_mission(tmp_path: Path, *, step_timeouts=None,
                         retry_policy=None, step_budgets=None) -> None:
    """Overwrite missions/build.yaml with the requested contract fields.

    We rebuild the yaml by hand from the seat definition so the file
    parses through the same subset parser used by the loader.
    """
    lines = [
        "schema: shiroe.mission/v1",
        "id: build",
        "version: 1",
        "",
        "triggers:",
        "  - build",
        "",
        "required_seats:",
        "  - id: planner",
        "    provides:",
        "      - architecture-planning",
        "      - dependency-analysis",
        "    permissions:",
        "      write: false",
        "    reasoning_class: deep",
        "  - id: implementer",
        "    provides:",
        "      - code-editing",
        "      - test-execution",
        "    permissions:",
        "      write: project",
        "    reasoning_class: balanced",
        "  - id: verifier",
        "    provides:",
        "      - code-review",
        "      - verification",
        "    permissions:",
        "      write: false",
        "    reasoning_class: balanced",
        "    constraints:",
        "      independent_from:",
        "        - implementer",
        "",
        "execution_sequence:",
        "  - planner",
        "  - implementer",
        "  - verifier",
        "",
        "required_outputs:",
        "  - implementation_plan",
        "  - changed_files",
        "  - verification_report",
        "",
        "completion:",
        "  all_steps_pass: true",
    ]
    if step_timeouts:
        lines.append("step_timeouts:")
        for k, v in step_timeouts.items():
            lines.append(f"  {k}: {v}")
    if retry_policy:
        lines.append("retry_policy:")
        for step, entry in retry_policy.items():
            lines.append(f"  {step}:")
            for k, v in entry.items():
                if isinstance(v, str):
                    lines.append(f"    {k}: {v}")
                else:
                    lines.append(f"    {k}: {v}")
    if step_budgets:
        lines.append("step_budgets:")
        for step, entry in step_budgets.items():
            lines.append(f"  {step}:")
            for k, v in entry.items():
                lines.append(f"    {k}: {v}")
    (tmp_path / "missions" / "build.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def _seed(tmp_path: Path, *, step_timeouts=None, retry_policy=None,
          step_budgets=None, policy_id: str = "balanced") -> str:
    for name in ("missions", "policies"):
        shutil.copytree(REPO_ROOT / name, tmp_path / name)
    _write_build_mission(
        tmp_path, step_timeouts=step_timeouts, retry_policy=retry_policy,
        step_budgets=step_budgets,
    )

    (tmp_path / ".shiroe" / "policy").mkdir(parents=True)
    (tmp_path / ".shiroe" / "policy" / "defaults.json").write_text(
        json.dumps({"allow": ["subprocess", "memory.write"]}), encoding="utf-8",
    )

    for name, provides in (
        ("architect", ["architecture-planning", "dependency-analysis"]),
        ("coder", ["code-editing", "test-execution"]),
        ("reviewer", ["code-review", "verification"]),
    ):
        src = tmp_path / "source" / name
        src.mkdir(parents=True)
        (src / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
        d = DiscoveredCapability(adapter="generic", root="<home>/skills",
                                 path=src, kind="skill")
        cid = register_discovery(tmp_path, d, trust=inspect_source(src))
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

    from shiroe.teams import compile_team
    plan = compile_team(tmp_path, task_id="task_pr14", mission_id="build",
                        policy_id=policy_id, active_harness="claude-code")
    return plan.run_id


def _ok(usage=None):
    def _inv(step_id, step_name, cap_id, ctx):
        return AdapterResult(ok=True, output=f"done:{step_name}",
                             exit_code=0, metadata={"enforcement_level": "A"},
                             usage=usage)
    return _inv


# ---------------------------------------------------------------------------
# SHR-055 — usage propagation
# ---------------------------------------------------------------------------

def test_usage_totals_aggregate_across_steps(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)
    usages = iter([
        {"tokens_in": 10, "tokens_out": 5,  "cost_usd": 0.01},
        {"tokens_in": 20, "tokens_out": 15, "cost_usd": 0.02},
        {"tokens_in": 30, "tokens_out": 25, "cost_usd": 0.03},
    ])

    def _inv(step_id, step_name, cap_id, ctx):
        return AdapterResult(ok=True, output="ok", usage=next(usages),
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"
    totals = result.budget["usage_totals"]
    assert totals["tokens_in"] == 60
    assert totals["tokens_out"] == 45
    assert totals["cost_usd"] == pytest.approx(0.06, abs=1e-6)


def test_missing_usage_treated_as_zero(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok(usage=None))
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"
    totals = result.budget["usage_totals"]
    assert totals == {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}


# ---------------------------------------------------------------------------
# SHR-056 — malformed output
# ---------------------------------------------------------------------------

def test_malformed_usage_fails_deterministically(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)

    def _inv(step_id, step_name, cap_id, ctx):
        # Negative tokens is a lying adapter.
        return AdapterResult(ok=True, output="x",
                             metadata={"enforcement_level": "A"},
                             usage={"tokens_in": -1, "tokens_out": 0, "cost_usd": 0.0})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "FAILED"
    assert "malformed adapter output" in (result.paused_reason or "")
    assert result.resume_token is not None


def test_malformed_adapter_result_fails_deterministically(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)

    def _inv(step_id, step_name, cap_id, ctx):
        return {"ok": True}  # not an AdapterResult at all

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "FAILED"
    assert "malformed adapter output" in (result.paused_reason or "")


# ---------------------------------------------------------------------------
# SHR-057 — per-step timeout
# ---------------------------------------------------------------------------

def _blocking_invoker(started: threading.Event):
    def _inv(step_id, step_name, cap_id, ctx):
        started.set()
        # Block until process exit; the supervisor's daemon-thread ceiling
        # unblocks its own wait deterministically.
        threading.Event().wait()
    return _inv


def test_step_timeout_from_mission_field(tmp_path: Path) -> None:
    run_id = _seed(tmp_path, step_timeouts={"planner": 1})
    started = threading.Event()
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_blocking_invoker(started))
    try:
        result = sup.run()
    finally:
        sup.close()
    assert started.is_set()
    assert result.state == "FAILED"
    assert result.paused_reason == "timeout"


def test_step_timeout_falls_through_to_default(tmp_path: Path) -> None:
    run_id = _seed(tmp_path)  # no step_timeouts declared
    started = threading.Event()

    def _inv(step_id, step_name, cap_id, ctx):
        started.set()
        threading.Event().wait()

    # Supervisor default is 600s — override on init to keep test fast.
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    # The mission-loaded default falls through to execution_steps.timeout_s
    # (600), then to SUPERVISOR_DEFAULT_TIMEOUT_S. Neither is friendly to
    # a unit test wall clock, so we thread a low ceiling in via the
    # execution_steps row the compiler wrote.
    import sqlite3
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        conn.execute(
            "UPDATE execution_steps SET timeout_s=1 WHERE run_id=?", (run_id,),
        )
        conn.commit()
    finally:
        conn.close()
    try:
        result = sup.run()
    finally:
        sup.close()
    assert started.is_set()
    assert result.state == "FAILED"
    assert result.paused_reason == "timeout"


# ---------------------------------------------------------------------------
# SHR-058 — retry policy
# ---------------------------------------------------------------------------

def test_retry_policy_exhausts_and_reports_last_error(tmp_path: Path) -> None:
    run_id = _seed(tmp_path, retry_policy={
        "planner": {"max_attempts": 3, "backoff": "none"},
    })
    calls = {"n": 0}

    def _inv(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        return AdapterResult(ok=False, error=f"attempt-{calls['n']}-boom",
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "FAILED"
    assert calls["n"] == 3  # exactly max_attempts, not one more, not one less
    assert result.paused_reason.startswith("retry_exhausted: ")
    assert "attempt-3-boom" in result.paused_reason


def test_retry_skipped_on_policy_deny(tmp_path: Path) -> None:
    run_id = _seed(tmp_path, retry_policy={
        "planner": {"max_attempts": 5, "backoff": "none"},
    })
    calls = {"n": 0}

    def _inv(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        return AdapterResult(
            ok=False, error="not allowed",
            metadata={"policy": {"verdict": "deny",
                                 "deciding_layer": "capability_gate"}},
        )

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    # Deny is terminal for the step — one invocation, not five.
    assert calls["n"] == 1
    assert result.state == "PAUSED_PERMISSION"


# ---------------------------------------------------------------------------
# SHR-063 — projected budget pause
# ---------------------------------------------------------------------------

def _tiny_budget_policy(tmp_path: Path, *, usd_max: float,
                        tokens_input_max: int, tokens_output_max: int) -> None:
    """Rewrite policies/lean.yaml with a budget small enough to trip
    projection on step 2. Compile references this policy by id.

    The whitelist ('lean'/'balanced'/'assured') is enforced by the policy
    schema — squatting on 'lean' is the smallest lever to get a custom
    envelope through validation.
    """
    (tmp_path / "policies" / "lean.yaml").write_text(
        "schema: shiroe.policy/v1\n"
        "id: lean\n"
        "version: 1\n"
        "max_parallel_workers: 1\n"
        "max_capabilities: 4\n"
        "independent_verifiers: 0\n"
        "autonomy_default: auto-safe\n"
        "reasoning_class_limits:\n"
        "  fast: unlimited\n"
        "  balanced: unlimited\n"
        "  deep: unlimited\n"
        "  frontier: unlimited\n"
        "cost_envelope:\n"
        f"  usd_max: {usd_max}\n"
        f"  tokens_input_max: {tokens_input_max}\n"
        f"  tokens_output_max: {tokens_output_max}\n"
        "description: test\n",
        encoding="utf-8",
    )


def test_budget_pause_on_projected_overrun(tmp_path: Path) -> None:
    # Every step projects 40 tokens_out; policy allows 60 → step 1 fits,
    # step 2's projection would push us past the ceiling before invoking.
    run_id = _seed(
        tmp_path,
        step_budgets={
            "planner": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "implementer": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "verifier": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
        },
    )
    # Swap the compiled run's policy to a tight envelope after the fact.
    _tiny_budget_policy(tmp_path, usd_max=100.0,
                        tokens_input_max=1_000_000, tokens_output_max=60)
    import sqlite3
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        conn.execute("UPDATE team_runs SET policy='lean' WHERE id=?", (run_id,))
        conn.commit()
    finally:
        conn.close()

    calls = {"n": 0, "steps": []}

    def _inv(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        calls["steps"].append(step_name)
        return AdapterResult(
            ok=True, output="ok", metadata={"enforcement_level": "A"},
            usage={"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
        )

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound, invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "PAUSED_BUDGET"
    assert "tokens_output_max" in (result.paused_reason or "")
    # Exactly one step invoked; step 2 gated by projection before invoke.
    assert calls["n"] == 1
    assert calls["steps"] == ["planner"]
    assert result.resume_token is not None


def test_resume_after_topup_produces_same_usage_totals(tmp_path: Path) -> None:
    # Control run: generous budget from the start.
    control_root = tmp_path / "control"
    control_root.mkdir()
    control_run = _seed(
        control_root,
        step_budgets={
            "planner": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "implementer": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "verifier": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
        },
    )
    _tiny_budget_policy(control_root, usd_max=100.0,
                        tokens_input_max=1_000_000, tokens_output_max=200)
    import sqlite3
    conn = sqlite3.connect(control_root / "memory" / "state" / "shiroe.sqlite")
    try:
        conn.execute("UPDATE team_runs SET policy='lean' WHERE id=?", (control_run,))
        conn.commit()
    finally:
        conn.close()

    def _inv_full(step_id, step_name, cap_id, ctx):
        return AdapterResult(
            ok=True, output="ok", metadata={"enforcement_level": "A"},
            usage={"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
        )

    sup = Supervisor(control_root, control_run,
                     mode=AutonomyMode.policy_bound, invoker=_inv_full)
    try:
        control_result = sup.run()
    finally:
        sup.close()
    assert control_result.state == "COMPLETED"
    control_totals = control_result.budget["usage_totals"]

    # Test run: budget starts tight (60), pauses after step 1, top up to
    # 200 and resume. Final usage_totals must byte-equal the control run.
    test_root = tmp_path / "test"
    test_root.mkdir()
    test_run = _seed(
        test_root,
        step_budgets={
            "planner": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "implementer": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
            "verifier": {"tokens_in": 0, "tokens_out": 40, "cost_usd": 0.0},
        },
    )
    _tiny_budget_policy(test_root, usd_max=100.0,
                        tokens_input_max=1_000_000, tokens_output_max=60)
    conn = sqlite3.connect(test_root / "memory" / "state" / "shiroe.sqlite")
    try:
        conn.execute("UPDATE team_runs SET policy='lean' WHERE id=?", (test_run,))
        conn.commit()
    finally:
        conn.close()

    sup = Supervisor(test_root, test_run,
                     mode=AutonomyMode.policy_bound, invoker=_inv_full)
    try:
        first = sup.run()
    finally:
        sup.close()
    assert first.state == "PAUSED_BUDGET"
    partial_totals = first.budget["usage_totals"]
    assert partial_totals["tokens_out"] == 40

    # Top up the budget (a fresh policy file with the same id).
    _tiny_budget_policy(test_root, usd_max=100.0,
                        tokens_input_max=1_000_000, tokens_output_max=200)
    result = resume(test_root, test_run, mode=AutonomyMode.policy_bound,
                    invoker=_inv_full)
    assert result.state == "COMPLETED"
    assert result.budget["usage_totals"] == control_totals


# ---------------------------------------------------------------------------
# SHR-057 — real-adapter path must not hit sqlite check_same_thread
# ---------------------------------------------------------------------------

def test_real_adapter_path_crosses_thread_boundary(tmp_path: Path) -> None:
    """Every other test injects a mocked ``invoker``, so the daemon-thread
    codepath that resolves and calls the built-in generic adapter is
    never exercised. Reach through it once end-to-end: without this,
    ``_resolve_adapter_for``'s reuse of ``self._conn`` from inside the
    timeout worker would raise ``sqlite3.ProgrammingError`` on the first
    step. The generic-skill adapter reads SKILL.md and returns it as
    Level-C context, which is enough to prove the step contract path
    survives the thread boundary.
    """
    run_id = _seed(tmp_path)
    result = Supervisor(tmp_path, run_id,
                        mode=AutonomyMode.policy_bound).run()
    assert result.state == "COMPLETED"
    assert result.completed_steps == list(BUILD_MISSION_STEPS)
