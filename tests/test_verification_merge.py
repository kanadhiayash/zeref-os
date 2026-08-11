"""PR15 gate — self-verification and concurrent-supervisor rejection.

SHR-059: If a run's assignments would let one seat verify its own
capability's work (verifier and implementer share a capability),
verification is refused with a specific, distinguishable state — not
a generic FAILED. Ordering, resume, and re-run must all keep refusing.

SHR-060/061: Two supervisors on the same ``run_id`` cannot both commit
canonical state. Detection is deterministic at commit time (owner_token
CAS + state_version CAS), not later at reconciliation.

The acceptance-gate wording lives in the PR15 brief; the on-disk spec
files (``SHIROE_FULL_FUNCTIONALITY_CLAUDE_HANDOFF.md``,
``SHR_BACKLOG_COVERAGE_MATRIX.csv``, ``SHIROE_EXECUTION_PROGRAM.json``)
do not exist in this tree, so this file also serves as the executable
statement of what the gate promises.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import threading
from pathlib import Path

import pytest

from shiroe.adapters.capabilities.base import AdapterResult
from shiroe.capabilities import approve, inspect_source, register_discovery
from shiroe.capabilities.discovery import DiscoveredCapability
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import AutonomyMode
from shiroe.runtime import (
    ConcurrentSupervisorError,
    Supervisor,
    resume,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Fixture — same shape as test_step_contracts._seed
# ---------------------------------------------------------------------------

def _write_build_mission(tmp_path: Path, *, include_independence: bool) -> None:
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
    ]
    if include_independence:
        lines += [
            "    constraints:",
            "      independent_from:",
            "        - implementer",
        ]
    lines += [
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
    (tmp_path / "missions" / "build.yaml").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def _seed(tmp_path: Path, *, include_independence: bool = True) -> str:
    for name in ("missions", "policies"):
        shutil.copytree(REPO_ROOT / name, tmp_path / name)
    _write_build_mission(tmp_path, include_independence=include_independence)
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
    plan = compile_team(tmp_path, task_id="task_pr15", mission_id="build",
                        policy_id="balanced", active_harness="claude-code")
    return plan.run_id


def _tamper_assignment(root: Path, run_id: str, seat_id: str,
                       target_seat_id: str) -> None:
    """Force ``seat_id``'s capability to match ``target_seat_id``'s.

    Mirrors what a malicious rewrite (or a broken external tool) would
    do post-compile — the resolver already prevents this at compile
    time, so the only way to exercise the runtime gate is to bypass it.
    """
    conn = sqlite3.connect(root / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT capability_id, capability_version_id "
            "FROM team_assignments WHERE run_id=? AND seat_id=?",
            (run_id, target_seat_id),
        ).fetchone()
        assert row is not None, f"no assignment for {target_seat_id!r}"
        target_cap, target_ver = row
        conn.execute(
            "UPDATE team_assignments SET capability_id=?, "
            "capability_version_id=? WHERE run_id=? AND seat_id=?",
            (target_cap, target_ver, run_id, seat_id),
        )
        conn.commit()
    finally:
        conn.close()


def _ok_invoker():
    def _inv(step_id, step_name, cap_id, ctx):
        return AdapterResult(ok=True, output=f"done:{step_name}",
                             metadata={"enforcement_level": "A"})
    return _inv


# ---------------------------------------------------------------------------
# SHR-059 — self-verification rejected
# ---------------------------------------------------------------------------

def test_self_verification_rejected_when_verifier_shares_capability(
    tmp_path: Path,
) -> None:
    run_id = _seed(tmp_path, include_independence=True)
    _tamper_assignment(tmp_path, run_id, "verifier", "implementer")

    calls = {"n": 0}
    def _inv(step_id, step_name, cap_id, ctx):
        calls["n"] += 1
        return AdapterResult(ok=True, output="x",
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_inv)
    try:
        result = sup.run()
    finally:
        sup.close()

    # Distinct terminal state, not a generic FAILED.
    assert result.state == "SELF_VERIFICATION_REJECTED"
    assert "self-verification" in (result.paused_reason or "")
    # No steps ran — the run refused before invoking anything.
    assert calls["n"] == 0
    assert result.completed_steps == []

    # The offending execution_step also ends in the distinct state.
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT state FROM execution_steps "
            "WHERE run_id=? AND step_name='verifier'",
            (run_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "SELF_VERIFICATION_REJECTED"


def test_self_verification_rejection_survives_rerun(tmp_path: Path) -> None:
    """Re-running the same tampered plan must keep refusing — not accept it
    on the second try, and not slip into a generic FAILED."""
    run_id = _seed(tmp_path, include_independence=True)
    _tamper_assignment(tmp_path, run_id, "verifier", "implementer")

    for _ in range(2):
        sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                         invoker=_ok_invoker())
        try:
            result = sup.run()
        finally:
            sup.close()
        assert result.state == "SELF_VERIFICATION_REJECTED"


def test_self_verification_survives_verifier_first_ordering(
    tmp_path: Path,
) -> None:
    """Reorder execution_sequence in the DB so the verifier row comes
    first — the mission-level independence constraint must still refuse
    the run."""
    run_id = _seed(tmp_path, include_independence=True)
    _tamper_assignment(tmp_path, run_id, "verifier", "implementer")

    # Swap rowid order: delete + re-insert verifier as the first row.
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        row = conn.execute(
            "SELECT id, dependency_ids, state, retries, timeout_s, "
            "permissions, input_hash, output_hash, started_at, ended_at "
            "FROM execution_steps WHERE run_id=? AND step_name='verifier'",
            (run_id,),
        ).fetchone()
        assert row is not None
        conn.execute(
            "DELETE FROM execution_steps WHERE run_id=? AND step_name='verifier'",
            (run_id,),
        )
        # Reinsert with a low-rowid trick — SQLite hands out MAX(rowid)+1,
        # so use an explicit rowid to force the verifier to the front.
        conn.execute(
            "INSERT INTO execution_steps (rowid, id, run_id, step_name, "
            "dependency_ids, state, retries, timeout_s, permissions, "
            "input_hash, output_hash, started_at, ended_at) "
            "VALUES (?, ?, ?, 'verifier', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (0, row[0], run_id, row[1], row[2], row[3], row[4], row[5],
             row[6], row[7], row[8], row[9]),
        )
        conn.commit()
    finally:
        conn.close()

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker())
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "SELF_VERIFICATION_REJECTED"


def test_clean_assignment_still_runs(tmp_path: Path) -> None:
    """Sanity: an untampered run completes normally — the runtime gate
    does not fire on well-formed plans."""
    run_id = _seed(tmp_path, include_independence=True)
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker())
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"
    assert result.completed_steps == ["planner", "implementer", "verifier"]


# ---------------------------------------------------------------------------
# SHR-060/061 — concurrent supervisors rejected
# ---------------------------------------------------------------------------

def test_second_supervisor_refused_on_owner_token_claim(tmp_path: Path) -> None:
    run_id = _seed(tmp_path, include_independence=True)

    # Simulate: sup_A has claimed but not finished. We can't easily stop
    # a run mid-flight in a portable test, so poke the token directly.
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        conn.execute(
            "UPDATE team_runs SET owner_token='sup_A_holds_it' WHERE id=?",
            (run_id,),
        )
        conn.commit()
    finally:
        conn.close()

    sup_b = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                       invoker=_ok_invoker())
    try:
        with pytest.raises(ConcurrentSupervisorError) as exc:
            sup_b.run()
    finally:
        sup_b.close()
    assert "sup_A_holds_it" in str(exc.value)

    # The run state is untouched — no half-committed transitions.
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        state, owner, ver = conn.execute(
            "SELECT state, owner_token, state_version "
            "FROM team_runs WHERE id=?", (run_id,),
        ).fetchone()
    finally:
        conn.close()
    assert state == "COMPILED"
    assert owner == "sup_A_holds_it"
    assert ver == 0


def test_owner_token_cas_detects_stolen_claim(tmp_path: Path) -> None:
    """A peer forcibly rewrites owner_token mid-run. The next state
    transition's CAS (both state_version AND owner_token in the WHERE
    clause) fails at commit time — the supervisor learns immediately,
    not at some later reconciliation pass."""
    run_id = _seed(tmp_path, include_independence=True)

    steps_seen: list[str] = []

    def _inv(step_id, step_name, cap_id, ctx):
        steps_seen.append(step_name)
        if step_name == "implementer":
            # A rogue writer overwrites owner_token. Under WAL the
            # update from another connection is serialized; when our
            # next _set_run_state runs its CAS, the WHERE clause on
            # owner_token=<ours> matches zero rows.
            other = sqlite3.connect(
                tmp_path / "memory" / "state" / "shiroe.sqlite"
            )
            try:
                other.execute(
                    "UPDATE team_runs SET owner_token='hostile_writer' "
                    "WHERE id=?", (run_id,),
                )
                other.commit()
            finally:
                other.close()
        return AdapterResult(ok=True, output="x",
                             metadata={"enforcement_level": "A"})

    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_inv)
    with pytest.raises(ConcurrentSupervisorError) as exc:
        try:
            sup.run()
        finally:
            sup.close()
    assert "CAS" in str(exc.value)
    assert "hostile_writer" in str(exc.value)
    # Steps ran before the theft; the guarantee is that the next
    # state-changing commit surfaces the loss.
    assert "planner" in steps_seen


def test_ownership_released_on_terminal_completion(tmp_path: Path) -> None:
    """After a successful run, owner_token is cleared so resume/audit
    tools do not see a phantom claim."""
    run_id = _seed(tmp_path, include_independence=True)
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker())
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "COMPLETED"
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        owner = conn.execute(
            "SELECT owner_token FROM team_runs WHERE id=?", (run_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert owner is None


def test_ownership_released_on_self_verification_rejection(
    tmp_path: Path,
) -> None:
    """A rejected run is terminal — releasing the token lets an operator
    inspect/rewrite without a stale claim in the way."""
    run_id = _seed(tmp_path, include_independence=True)
    _tamper_assignment(tmp_path, run_id, "verifier", "implementer")
    sup = Supervisor(tmp_path, run_id, mode=AutonomyMode.policy_bound,
                     invoker=_ok_invoker())
    try:
        result = sup.run()
    finally:
        sup.close()
    assert result.state == "SELF_VERIFICATION_REJECTED"
    conn = sqlite3.connect(tmp_path / "memory" / "state" / "shiroe.sqlite")
    try:
        owner = conn.execute(
            "SELECT owner_token FROM team_runs WHERE id=?", (run_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert owner is None
