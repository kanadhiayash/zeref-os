"""Supervisor — drives a compiled team plan through the RUN state machine.

This module intentionally keeps dispatcher / retries / recovery / events
in one file because the logic is a single sequential loop over
execution_steps rows; splitting it further would add indirection without
clarity.
"""

from __future__ import annotations

import queue
import sqlite3
import threading
import time
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


# SHR-057: supervisor-level fallback timeout when neither mission nor
# per-step field is set. 10 minutes matches the value the compiler writes
# to execution_steps.timeout_s.
SUPERVISOR_DEFAULT_TIMEOUT_S = 600


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
    # SHR-058/063: opaque handle for the paused / failed step. `None`
    # when the run reached a terminal success. Resume ignores it —
    # it's a determinism witness for callers that want to prove two
    # runs paused at the same seam.
    resume_token: str | None = None


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
        self._budget = _load_budget(self._conn, run_id, root=self.root)
        self._mission = _load_mission_safely(self.root, self._conn, run_id)

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------
    # Mission-driven per-step contract lookups (SHR-057/058/063)
    # ------------------------------------------------------------------
    def _step_timeout_s(self, step_name: str, fallback: int | None) -> int:
        if self._mission is not None:
            explicit = self._mission.step_timeouts.get(step_name)
            if explicit:
                return int(explicit)
        if fallback and fallback > 0:
            return int(fallback)
        return SUPERVISOR_DEFAULT_TIMEOUT_S

    def _step_projection(self, step_name: str) -> dict:
        if self._mission is not None:
            entry = self._mission.step_budgets.get(step_name)
            if entry:
                return entry
        return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    def _step_max_attempts(self, step_name: str, default: int) -> int:
        if self._mission is not None:
            entry = self._mission.retry_policy.get(step_name)
            if entry:
                return int(entry["max_attempts"])
        return default

    def _step_backoff_s(self, step_name: str) -> float:
        if self._mission is not None:
            entry = self._mission.retry_policy.get(step_name)
            if entry and entry.get("backoff") == "fixed":
                return float(entry.get("backoff_s", 0.0) or 0.0)
        return 0.0

    def _persist_usage(self) -> None:
        """Mirror aggregated usage into team_runs so a Supervisor started
        in a later process/session picks up prior spend and resume is
        byte-equal to a control run that had the budget from the start."""
        self._conn.execute(
            "UPDATE team_runs SET cost_usd=?, tokens_input=?, tokens_output=? "
            "WHERE id=?",
            (self._budget.usd_spent, self._budget.tokens_input_spent,
             self._budget.tokens_output_spent, self.run_id),
        )
        self._conn.commit()

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
        # Called from inside the timeout worker thread (see
        # _invoke_with_timeout), so it MUST NOT reuse self._conn — that
        # connection was opened on the main thread and sqlite3's default
        # check_same_thread=True would raise ProgrammingError. Open a
        # short-lived, thread-local connection to the same WAL-mode file.
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(self._db.path, timeout=5.0)
        try:
            row = conn.execute(
                "SELECT manifest FROM capability_versions "
                "WHERE capability_id=? ORDER BY created_at DESC LIMIT 1",
                (capability_id,),
            ).fetchone()
        finally:
            conn.close()
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

    def _invoke_with_timeout(self, timeout_s: int, step_id: str,
                             step_name: str, capability_id: str
                             ) -> tuple[AdapterResult | None, BaseException | None]:
        """Run ``_invoke_step`` on a daemon thread and enforce a wall-clock
        ceiling deterministically.

        Signal-based alarms don't cross threads and won't be portable;
        ThreadPoolExecutor's ``__exit__`` blocks waiting for the worker to
        finish, which defeats the ceiling when the adapter is stuck. A
        daemon thread + queue.get(timeout) returns as soon as the ceiling
        hits and lets the process exit cleanly.

        Returns ``(result, None)`` on success, ``(None, exc)`` if the
        adapter raised, or ``(None, TimeoutError)`` on wall-clock overrun.
        """
        q: queue.Queue = queue.Queue(maxsize=1)

        def _run() -> None:
            try:
                q.put(("ok", self._invoke_step(step_id, step_name, capability_id)))
            except BaseException as exc:  # noqa: BLE001 — must reach parent
                q.put(("err", exc))

        t = threading.Thread(target=_run, daemon=True,
                             name=f"shiroe-step-{step_id}")
        t.start()
        try:
            kind, val = q.get(timeout=max(0.001, float(timeout_s)))
        except queue.Empty:
            return None, TimeoutError("timeout")
        if kind == "err":
            return None, val
        return val, None

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
            # Running-total budget check before every step
            reason = self._budget.exceeded()
            if reason:
                self._set_run_state("PAUSED_BUDGET", reason=reason)
                self._persist_usage()
                return RunResult(self.run_id, "PAUSED_BUDGET",
                                 completed, paused_reason=reason,
                                 budget=self._budget.snapshot(),
                                 resume_token=step_id)

            # SHR-063: conservative projected-cost gate. If the step's
            # declared upper bound cannot fit inside remaining budget, we
            # pause BEFORE invoking — no invocation, no half-step spend.
            projection = self._step_projection(step_name)
            projected = self._budget.would_exceed(projection)
            if projected:
                self._set_run_state("PAUSED_BUDGET", reason=projected)
                self._persist_usage()
                return RunResult(self.run_id, "PAUSED_BUDGET",
                                 completed, paused_reason=projected,
                                 budget=self._budget.snapshot(),
                                 resume_token=step_id)

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

            timeout = self._step_timeout_s(step_name, timeout_s)
            # SHR-058: max_attempts falls back to the old max_retries
            # semantics (1 initial + N-1 retries).
            max_attempts = self._step_max_attempts(step_name, default=max_retries)
            backoff = self._step_backoff_s(step_name)

            attempt = 0
            last_error: str | None = None
            while True:
                attempt += 1
                result, exc = self._invoke_with_timeout(
                    timeout, step_id, step_name, cap_id,
                )
                # SHR-057: wall-clock ceiling hit — deterministic FAILED
                # with reason="timeout". No enum invented; state machine
                # gets RUNNING → TIMED_OUT → FAILED so both the step and
                # run rows read cleanly.
                if isinstance(exc, TimeoutError):
                    self._set_step_state(step_id, "TIMED_OUT", reason="timeout")
                    self._set_step_state(step_id, "FAILED", reason="timeout")
                    self._set_run_state("FAILED", reason="timeout")
                    self._persist_usage()
                    return RunResult(self.run_id, "FAILED", completed,
                                     paused_reason="timeout",
                                     budget=self._budget.snapshot(),
                                     resume_token=step_id)
                if exc is not None:
                    # An adapter raising isn't a step contract branch —
                    # let it propagate to whatever the caller was doing
                    # (the resume test already leans on KeyboardInterrupt
                    # escaping cleanly).
                    raise exc

                # SHR-056: shape validation. A non-AdapterResult, or an
                # AdapterResult that lies (ok=True + error, or malformed
                # usage) both route to FAILED with a distinctive reason.
                malformed = _validate_result(result)
                if malformed:
                    self._set_step_state(step_id, "FAILED", reason=malformed)
                    self._set_run_state("FAILED", reason=malformed)
                    self._persist_usage()
                    return RunResult(self.run_id, "FAILED", completed,
                                     paused_reason=malformed,
                                     budget=self._budget.snapshot(),
                                     resume_token=step_id)

                # SHR-055: aggregate adapter-reported usage. None means
                # zero, truthful. Malformed already died above.
                self._budget.charge(**_usage_charge(result.usage))

                if result.ok:
                    break

                # Policy denial short-circuits retry — a deny verdict is
                # not a transient error; retrying would just replay the
                # same permission decision.
                verdict = (result.metadata or {}).get("policy", {}).get("verdict")
                if verdict in ("deny", "require_approval"):
                    self._set_step_state(step_id, "PERMISSION_DENIED",
                                         reason=result.error)
                    self._set_run_state("PAUSED_PERMISSION", reason=result.error)
                    self._persist_usage()
                    return RunResult(self.run_id, "PAUSED_PERMISSION",
                                     completed, paused_reason=result.error,
                                     budget=self._budget.snapshot(),
                                     resume_token=step_id)

                last_error = result.error
                if attempt >= max_attempts:
                    reason = f"retry_exhausted: {last_error}"
                    self._set_step_state(step_id, "FAILED", reason=reason)
                    self._set_run_state("FAILED", reason=reason)
                    self._persist_usage()
                    return RunResult(self.run_id, "FAILED", completed,
                                     paused_reason=reason,
                                     budget=self._budget.snapshot(),
                                     resume_token=step_id)
                # Retry: bounce through RETRYABLE_FAILURE → READY → RUNNING
                # (state machine forbids RUNNING → RUNNING) and apply the
                # deterministic backoff.
                self._set_step_state(step_id, "RETRYABLE_FAILURE",
                                     reason=result.error)
                self._conn.execute(
                    "UPDATE execution_steps SET retries=retries+1, state='READY' "
                    "WHERE id=?", (step_id,),
                )
                self._conn.commit()
                self._set_step_state(step_id, "RUNNING")
                if backoff > 0:
                    time.sleep(backoff)

            # OUTPUT_RECEIVED → VALIDATING → PASSED
            self._set_step_state(step_id, "OUTPUT_RECEIVED")
            self._set_step_state(step_id, "VALIDATING")
            self._set_step_state(step_id, "PASSED")
            self._persist_usage()
            completed.append(step_name)

        # All steps done
        self._set_run_state("VERIFYING")
        self._set_run_state("COMPLETED")
        self._persist_usage()
        return RunResult(self.run_id, "COMPLETED", completed,
                         budget=self._budget.snapshot(),
                         resume_token=None)


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

def _load_budget(conn: sqlite3.Connection, run_id: str,
                 *, root: Path | None = None) -> BudgetTracker:
    # For PR 8, budget lives on the policy (loaded fresh from disk). Runs
    # store their policy id in `team_runs.policy`. Persisted spend on
    # `team_runs` is folded back into the tracker so a Supervisor started
    # in a later process — the resume path — sees prior spend and
    # produces the same usage_totals as a control run.
    row = conn.execute(
        "SELECT policy, cost_usd, tokens_input, tokens_output "
        "FROM team_runs WHERE id=?", (run_id,),
    ).fetchone()
    if row is None:
        return BudgetTracker(usd_max=0.0, tokens_input_max=0, tokens_output_max=0)
    policy_id, usd_spent, tin_spent, tout_spent = row
    # Import here to avoid startup cost
    from shiroe.execution_policies import get_policy
    from shiroe.memory import MemoryRoot
    try:
        # Prefer the caller's root (isolated test worktrees, subprocesses
        # deep inside a repo); fall back to discovery for legacy callers.
        policy_root = Path(root) if root is not None else MemoryRoot.discover().root
        policy = get_policy(policy_root, policy_id)
        usd_max = float(policy.cost_envelope.get("usd_max", 0.0))
        tin_max = int(policy.cost_envelope.get("tokens_input_max", 0))
        tout_max = int(policy.cost_envelope.get("tokens_output_max", 0))
    except (KeyError, FileNotFoundError):
        usd_max, tin_max, tout_max = 100.0, 10_000_000, 10_000_000
    return BudgetTracker(
        usd_max=usd_max,
        tokens_input_max=tin_max,
        tokens_output_max=tout_max,
        usd_spent=float(usd_spent or 0.0),
        tokens_input_spent=int(tin_spent or 0),
        tokens_output_spent=int(tout_spent or 0),
    )


def _load_mission_safely(root: Path, conn: sqlite3.Connection, run_id: str):
    """Best-effort mission lookup used for step-contract fields.

    Absent mission (older runs, missing on-disk file, missions/ not
    present) means every per-step field falls through to its supervisor
    default — the run still executes.
    """
    row = conn.execute(
        "SELECT mission_id FROM team_runs WHERE id=?", (run_id,),
    ).fetchone()
    if row is None or not row[0]:
        return None
    try:
        from shiroe.missions import get_mission
        return get_mission(root, row[0])
    except (KeyError, FileNotFoundError, Exception):  # noqa: BLE001
        return None


def _validate_result(result) -> str | None:
    """SHR-056: distinctive reason on malformed adapter output, else None.

    Every path returns a string that includes the phrase 'malformed
    adapter output' so callers and log readers can distinguish it from
    an honest transient failure.
    """
    if not isinstance(result, AdapterResult):
        return (f"malformed adapter output: expected AdapterResult, got "
                f"{type(result).__name__}")
    if result.ok and result.error:
        return "malformed adapter output: ok=True with error set"
    usage = result.usage
    if usage is None:
        return None
    if not isinstance(usage, dict):
        return (f"malformed adapter output: usage must be dict or None, "
                f"got {type(usage).__name__}")
    for key in ("tokens_in", "tokens_out", "cost_usd"):
        if key not in usage:
            return f"malformed adapter output: usage missing {key!r}"
        v = usage[key]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            return f"malformed adapter output: usage[{key!r}] not numeric"
        if v < 0:
            return f"malformed adapter output: usage[{key!r}] negative"
    return None


def _usage_charge(usage: dict | None) -> dict:
    """SHR-055: normalize an AdapterResult.usage to BudgetTracker kwargs."""
    if not usage:
        return {"usd": 0.0, "tokens_input": 0, "tokens_output": 0}
    return {
        "usd": float(usage.get("cost_usd", 0.0)),
        "tokens_input": int(usage.get("tokens_in", 0)),
        "tokens_output": int(usage.get("tokens_out", 0)),
    }


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
