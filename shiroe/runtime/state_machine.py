"""RUN + STEP state machines (vNext §10.1, §10.2)."""

from __future__ import annotations


RUN_STATES = (
    "CREATED", "COMPILED", "AUTHORIZED", "RUNNING", "VERIFYING",
    "COMPLETED",
    "PAUSED_PERMISSION", "PAUSED_BUDGET", "RETRYING", "DEGRADED",
    "FAILED", "CANCELLED",
    # SHR-059: distinct terminal state for self-verification refusal so
    # log readers don't confuse it with a generic FAILED.
    "SELF_VERIFICATION_REJECTED",
)

STEP_STATES = (
    "PENDING", "READY", "RUNNING", "OUTPUT_RECEIVED", "VALIDATING",
    "PASSED",
    "TIMED_OUT", "RETRYABLE_FAILURE", "PERMISSION_DENIED",
    "INVALID_OUTPUT", "FAILED", "SKIPPED",
    # SHR-059: the verifier step refuses to execute because its
    # capability matches an ``independent_from`` peer. Terminal.
    "SELF_VERIFICATION_REJECTED",
)


_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED":            frozenset({"COMPILED", "CANCELLED"}),
    "COMPILED":           frozenset({"AUTHORIZED", "CANCELLED"}),
    "AUTHORIZED":         frozenset({"RUNNING", "PAUSED_PERMISSION",
                                     "PAUSED_BUDGET", "CANCELLED"}),
    "RUNNING":            frozenset({"VERIFYING", "PAUSED_PERMISSION",
                                     "PAUSED_BUDGET", "RETRYING",
                                     "DEGRADED", "FAILED", "CANCELLED",
                                     "SELF_VERIFICATION_REJECTED"}),
    "VERIFYING":          frozenset({"COMPLETED", "RUNNING", "FAILED",
                                     "DEGRADED", "CANCELLED"}),
    "PAUSED_PERMISSION":  frozenset({"RUNNING", "CANCELLED"}),
    "PAUSED_BUDGET":      frozenset({"RUNNING", "CANCELLED"}),
    "RETRYING":           frozenset({"RUNNING", "FAILED", "CANCELLED"}),
    "DEGRADED":           frozenset({"RUNNING", "FAILED", "CANCELLED"}),
    "COMPLETED":          frozenset(),
    "FAILED":             frozenset(),
    "CANCELLED":          frozenset(),
    "SELF_VERIFICATION_REJECTED": frozenset(),
}


_STEP_TRANSITIONS: dict[str, frozenset[str]] = {
    "PENDING":            frozenset({"READY", "SKIPPED",
                                     "SELF_VERIFICATION_REJECTED"}),
    "READY":              frozenset({"RUNNING", "SKIPPED",
                                     "SELF_VERIFICATION_REJECTED"}),
    "RUNNING":            frozenset({"OUTPUT_RECEIVED", "TIMED_OUT",
                                     "RETRYABLE_FAILURE",
                                     "PERMISSION_DENIED", "FAILED"}),
    "OUTPUT_RECEIVED":    frozenset({"VALIDATING", "FAILED"}),
    "VALIDATING":         frozenset({"PASSED", "INVALID_OUTPUT", "FAILED"}),
    "TIMED_OUT":          frozenset({"RETRYABLE_FAILURE", "FAILED"}),
    "RETRYABLE_FAILURE":  frozenset({"READY", "FAILED"}),
    "PERMISSION_DENIED":  frozenset({"READY", "FAILED", "SKIPPED"}),
    "INVALID_OUTPUT":     frozenset({"RETRYABLE_FAILURE", "FAILED"}),
    "PASSED":             frozenset(),
    "FAILED":             frozenset(),
    "SKIPPED":            frozenset(),
    "SELF_VERIFICATION_REJECTED": frozenset(),
}


class INVALID_RUN_TRANSITION(ValueError):  # noqa: N801 — exported as class
    pass


class INVALID_STEP_TRANSITION(ValueError):  # noqa: N801
    pass


def can_run_transition(current: str, target: str) -> bool:
    return target in _RUN_TRANSITIONS.get(current, frozenset())


def can_step_transition(current: str, target: str) -> bool:
    return target in _STEP_TRANSITIONS.get(current, frozenset())


def assert_run_transition(current: str, target: str) -> None:
    if not can_run_transition(current, target):
        raise INVALID_RUN_TRANSITION(
            f"invalid RUN transition {current!r} → {target!r}"
        )


def assert_step_transition(current: str, target: str) -> None:
    if not can_step_transition(current, target):
        raise INVALID_STEP_TRANSITION(
            f"invalid STEP transition {current!r} → {target!r}"
        )


# Steps that produce irreversible side effects must not be re-run on
# resume. The supervisor treats these terminal-succeeded states as
# "already done" — recovery.py picks the first non-terminal-succeeded step.
IRREVERSIBLE_TERMINAL_STEP_STATES: frozenset[str] = frozenset({
    "PASSED", "SKIPPED",
})
