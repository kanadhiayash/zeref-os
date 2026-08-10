"""Supervisor — drives a compiled team plan through the RUN state machine.

This module intentionally keeps dispatcher / retries / recovery / events
in one file because the logic is a single sequential loop over
execution_steps rows; splitting it further would add indirection without
clarity.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from shiroe.adapters.capabilities import (
    AdapterResult,
    resolve_adapter,
)
from shiroe.adapters.capabilities.base import CapabilityAdapter
from shiroe.capabilities import assert_executable
from shiroe.capabilities.gate import CapabilityGateError
from shiroe.capabilities.store import CapabilityStore
from shiroe.policy import AutonomyMode, evaluate as policy_evaluate
from shiroe.policy.schema import Action, ActionKind, Verdict
from shiroe.runtime.budget import BudgetTracker
from shiroe.runtime.state_machine import (
    IRREVERSIBLE_TERMINAL_STEP_STATES,
    assert_run_transition,
    assert_step_transition,
    can_step_transition,
)
from shiroe.storage import EventEnvelope, EventLog, StateDB


class SupervisorError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class RunResult:
    run_id: str
    state: str
    completed_steps: list[str]
    paused_reason: str | None = None
    budget: dict | None = None


# The invoker allows tests to swap out the adapter fully. Default is the
# real adapter registry, which itself gates through shiroe.policy and
# shiroe.capabilities.assert_executable.
Invoker = Callable[[str, str, str, dict], AdapterResult]


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------

class Supervisor:
    def __init__(self, root: Path | str, run_id: str,
                 *, mode: AutonomyMode = AutonomyMode.auto_safe,
                 invoker: Invoker | None = None):
        self.root = Path(root)
        self.run_id = run_id
        self.mode = mode
        self._invoker = invoker
        self._db = StateDB(self.root)
        self._db.migrate()
        self._conn = self._db.connect()
        self._events = EventLog(self.root, mirror_conn=self._conn)
        self._budget = _load_budget(self._conn, run_id)

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------
    def _set_run_state(self, target: str, *, reason: str | None = None) -> None:
        row = self._conn.execute(
            "SELECT state FROM team_runs WHERE id=?", (self.run_id,),
        ).fetchone()
        current = row[0] if row else "CREATED"
        assert_run_transition(current, target)
        self._conn.execute(
            "UPDATE team_runs SET state=?, ended_at=CASE WHEN ? IN "
            "('COMPLETED','FAILED','CANCELLED') THEN ? ELSE ended_at END "
            "WHERE id=?",
            (target, target, _now(), self.run_id),
        )
        self._conn.commit()
        event_type = _RUN_EVENT_TYPE.get(target, "run.paused")
        self._events.append(EventEnvelope(
            event_type=event_type, actor="supervisor",
            target=f"run:{self.run_id}",
            payload={"from": current, "to": target, "reason": reason},
        ))

    def _set_step_state(self, step_id: str, target: str,
                        *, reason: str | None = None) -> None:
        current_row = self._conn.execute(
            "SELECT step_name, state FROM execution_steps WHERE id=?",
            (step_id,),
        ).fetchone()
        step_name, current = current_row
        assert_step_transition(current, target)
        self._conn.execute(
            "UPDATE execution_steps SET state=?, "
            "started_at=CASE WHEN ?='RUNNING' AND started_at IS NULL "
            "                THEN ? ELSE started_at END, "
            "ended_at=CASE WHEN ? IN ('PASSED','FAILED','SKIPPED','TIMED_OUT') "
            "              THEN ? ELSE ended_at END "
            "WHERE id=?",
            (target, target, _now(), target, _now(), step_id),
        )
        self._conn.commit()
        event_type = _STEP_EVENT_TYPE.get(target)
        if event_type is None:
            # transitional states without a whitelisted event — log a step.started catch-all
            if current == "READY" and target == "RUNNING":
                event_type = "step.started"
            elif target in ("FAILED", "PERMISSION_DENIED", "TIMED_OUT", "INVALID_OUTPUT"):
                event_type = "step.failed"
            elif target == "PASSED":
                event_type = "step.completed"
            elif target == "RETRYABLE_FAILURE":
                event_type = "step.retried"
            else:
                event_type = "step.started"
        self._events.append(EventEnvelope(
            event_type=event_type, actor="supervisor",
            target=f"step:{step_id}",
            payload={"step": step_name, "from": current, "to": target,
                     "reason": reason},
        ))

    # ------------------------------------------------------------------
    def _load_assignments(self) -> dict[str, dict]:
        rows = self._conn.execute(
            "SELECT seat_id, capability_id, capability_version_id, score "
            "FROM team_assignments WHERE run_id=?",
            (self.run_id,),
        ).fetchall()
        return {
            seat: {"capability_id": cap, "version_id": ver, "score": score}
            for seat, cap, ver, score in rows
        }

    def _load_steps(self) -> list[tuple]:
        return self._conn.execute(
            "SELECT id, step_name, state, retries, timeout_s "
            "FROM execution_steps WHERE run_id=? ORDER BY rowid",
            (self.run_id,),
        ).fetchall()

    def _resolve_adapter_for(self, capability_id: str) -> CapabilityAdapter:
        row = self._conn.execute(
            "SELECT manifest FROM capability_versions "
            "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
            (capability_id,),
        ).fetchone()
        if row is None:
            raise SupervisorError(f"no manifest for {capability_id!r}")
        import json as _json
        adapter_name = _json.loads(row[0]).get("entrypoint", {}).get("adapter") \
            or "generic"
        return resolve_adapter(adapter_name)

    def _invoke_step(self, step_id: str, step_name: str,
                     capability_id: str) -> AdapterResult:
        # Adapter invocation runs through the policy engine already, plus a
        # capability-gate assert here so revocation / digest drift mid-run
        # trips instantly. The gate recomputes the on-disk digest and
        # re-quarantines on drift; if the capability was revoked between
        # steps the lifecycle check catches it. Flagging the result with a
        # policy `deny` verdict routes through the PERMISSION_DENIED /
        # PAUSED_PERMISSION path so the run halts with a specific state
        # (not a generic post-retry FAILED).
        try:
            assert_executable(self.root, capability_id)
        except CapabilityGateError as e:
            return AdapterResult(
                ok=False,
                error=f"capability gate: {e}",
                metadata={"policy": {"verdict": "deny",
                                     "deciding_layer": "capability_gate"}},
            )

        # Pre-flight policy check on memory.write (every step writes a
        # `step.completed` event).
        stack_action = Action(ActionKind.memory_write,
                              target=f"step:{step_id}")
        from shiroe.policy import load_policy_stack
        stack = load_policy_stack(self.root)
        decision = policy_evaluate(stack_action, stack, mode=self.mode)
        if decision.verdict is not Verdict.allow:
            return AdapterResult(
                ok=False,
                error=f"policy {decision.verdict.value} at {decision.deciding_layer}: {decision.reason}",
                metadata={"policy": {"verdict": decision.verdict.value,
                                     "deciding_layer": decision.deciding_layer}},
            )

        if self._invoker is not None:
            return self._invoker(step_id, step_name, capability_id,
                                 {"root": str(self.root)})
        adapter = self._resolve_adapter_for(capability_id)
        return adapter.invoke(
            capability_id=capability_id, action=step_name,
            inputs={"root": str(self.root),
                    "autonomy_mode": self.mode.value},
        )

    # ------------------------------------------------------------------
    def run(self, *, max_retries: int = 2) -> RunResult:
        current_row = self._conn.execute(
            "SELECT state FROM team_runs WHERE id=?", (self.run_id,),
        ).fetchone()
        if current_row is None:
            raise SupervisorError(f"unknown run {self.run_id!r}")
        current = current_row[0]
        # Move into AUTHORIZED then RUNNING (only from COMPILED)
        if current == "COMPILED":
            self._set_run_state("AUTHORIZED")
            current = "AUTHORIZED"
        if current in ("AUTHORIZED", "PAUSED_PERMISSION", "PAUSED_BUDGET",
                        "RETRYING", "DEGRADED"):
            self._set_run_state("RUNNING")
        # If a previous invocation was interrupted mid-step, the run's state
        # is already RUNNING; nothing to transition. Any step left in a
        # non-terminal state (RUNNING/READY/OUTPUT_RECEIVED/VALIDATING) gets
        # reset to PENDING so the loop can drive it through the state
        # machine cleanly. Completed steps (PASSED/SKIPPED) stay put — the
        # PR-8 acceptance gate says they must NOT re-run on resume.
        self._conn.execute(
            "UPDATE execution_steps "
            "   SET state='PENDING', started_at=NULL, ended_at=NULL "
            " WHERE run_id=? "
            "   AND state IN ('READY','RUNNING','OUTPUT_RECEIVED',"
            "                 'VALIDATING','RETRYABLE_FAILURE',"
            "                 'PERMISSION_DENIED','TIMED_OUT',"
            "                 'INVALID_OUTPUT')",
            (self.run_id,),
        )
        self._conn.commit()

        assignments = self._load_assignments()
        step_seat_map = list(assignments.keys())  # order matches insertion

        completed: list[str] = []
        for step_id, step_name, state, retries, timeout_s in self._load_steps():
            if state in IRREVERSIBLE_TERMINAL_STEP_STATES:
                completed.append(step_name)
                continue
            # Budget check before every step
            reason = self._budget.exceeded()
            if reason:
                self._set_run_state("PAUSED_BUDGET", reason=reason)
                return RunResult(self.run_id, "PAUSED_BUDGET",
                                 completed, paused_reason=reason,
                                 budget=self._budget.snapshot())

            # Resolve step name → seat assignment. Missions declare seats
            # in the order they appear in execution_sequence, which matches
            # step_name for the sample missions.
            seat = step_name if step_name in assignments else step_seat_map[
                min(len(completed), len(step_seat_map) - 1)
            ]
            cap_id = assignments[seat]["capability_id"]

            # PENDING → READY → RUNNING
            if state == "PENDING":
                self._set_step_state(step_id, "READY")
            self._set_step_state(step_id, "RUNNING")

            result = self._invoke_step(step_id, step_name, cap_id)
            # Charge a nominal token estimate. Real accounting comes with
            # PR 12/13 harness adapters.
            self._budget.charge(usd=0.001, tokens_input=100, tokens_output=100)

            if not result.ok:
                # Policy denial → PAUSED_PERMISSION at run level
                if result.metadata.get("policy", {}).get("verdict") in ("deny", "require_approval"):
                    self._set_step_state(step_id, "PERMISSION_DENIED",
                                         reason=result.error)
                    self._set_run_state("PAUSED_PERMISSION", reason=result.error)
                    return RunResult(self.run_id, "PAUSED_PERMISSION",
                                     completed, paused_reason=result.error,
                                     budget=self._budget.snapshot())
                # Retry logic
                if retries < max_retries:
                    self._set_step_state(step_id, "RETRYABLE_FAILURE",
                                         reason=result.error)
                    self._conn.execute(
                        "UPDATE execution_steps SET retries=retries+1, state='READY' "
                        "WHERE id=?", (step_id,),
                    )
                    self._conn.commit()
                    # re-run same step
                    self._set_step_state(step_id, "RUNNING")
                    result = self._invoke_step(step_id, step_name, cap_id)
                    self._budget.charge(usd=0.001, tokens_input=100, tokens_output=100)
                    if not result.ok:
                        self._set_step_state(step_id, "FAILED", reason=result.error)
                        self._set_run_state("FAILED", reason=result.error)
                        return RunResult(self.run_id, "FAILED", completed,
                                         paused_reason=result.error,
                                         budget=self._budget.snapshot())
                else:
                    self._set_step_state(step_id, "FAILED", reason=result.error)
                    self._set_run_state("FAILED", reason=result.error)
                    return RunResult(self.run_id, "FAILED", completed,
                                     paused_reason=result.error,
                                     budget=self._budget.snapshot())

            # OUTPUT_RECEIVED → VALIDATING → PASSED
            self._set_step_state(step_id, "OUTPUT_RECEIVED")
            self._set_step_state(step_id, "VALIDATING")
            self._set_step_state(step_id, "PASSED")
            completed.append(step_name)

        # All steps done
        self._set_run_state("VERIFYING")
        self._set_run_state("COMPLETED")
        return RunResult(self.run_id, "COMPLETED", completed,
                         budget=self._budget.snapshot())


# ---------------------------------------------------------------------------
# Event type helpers
# ---------------------------------------------------------------------------

_RUN_EVENT_TYPE = {
    "AUTHORIZED": "run.authorized",
    "RUNNING": "run.started",
    "VERIFYING": "run.started",   # no verifier-specific event yet
    "COMPLETED": "run.completed",
    "FAILED": "run.failed",
    "CANCELLED": "run.cancelled",
    "PAUSED_PERMISSION": "run.paused",
    "PAUSED_BUDGET": "run.paused",
    "RETRYING": "run.resumed",
    "DEGRADED": "run.paused",
}

_STEP_EVENT_TYPE = {
    "RUNNING": "step.started",
    "PASSED": "step.completed",
    "FAILED": "step.failed",
    "RETRYABLE_FAILURE": "step.retried",
}


# ---------------------------------------------------------------------------
# Budget loader — reads cost_envelope stored on the compiled plan
# ---------------------------------------------------------------------------

def _load_budget(conn: sqlite3.Connection, run_id: str) -> BudgetTracker:
    # For PR 8, budget lives on the policy (loaded fresh from disk). Runs
    # store their policy id in `team_runs.policy`.
    row = conn.execute(
        "SELECT policy FROM team_runs WHERE id=?", (run_id,),
    ).fetchone()
    if row is None:
        return BudgetTracker(usd_max=0.0, tokens_input_max=0, tokens_output_max=0)
    # Import here to avoid startup cost
    from shiroe.execution_policies import get_policy
    from shiroe.memory import MemoryRoot
    try:
        policy = get_policy(MemoryRoot.discover().root, row[0])
    except (KeyError, FileNotFoundError):
        return BudgetTracker(usd_max=100.0, tokens_input_max=10_000_000,
                             tokens_output_max=10_000_000)
    return BudgetTracker(
        usd_max=float(policy.cost_envelope.get("usd_max", 0.0)),
        tokens_input_max=int(policy.cost_envelope.get("tokens_input_max", 0)),
        tokens_output_max=int(policy.cost_envelope.get("tokens_output_max", 0)),
    )


# ---------------------------------------------------------------------------
# resume()
# ---------------------------------------------------------------------------

def resume(root: Path | str, run_id: str,
           *, mode: AutonomyMode = AutonomyMode.auto_safe,
           invoker: Invoker | None = None) -> RunResult:
    """Pick up a persisted run at the first non-PASSED/SKIPPED step."""
    sup = Supervisor(root, run_id, mode=mode, invoker=invoker)
    try:
        return sup.run()
    finally:
        sup.close()
