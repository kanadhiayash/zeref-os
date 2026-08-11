"""Mission schema + validator."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field


MISSION_SCHEMA = "shiroe.mission/v1"

# SHR-009: the ordered step list is a sequence, not a graph. Mission files
# written against the pre-rename name still load, warning exactly once.
SEQUENCE_FIELD = "execution_sequence"
LEGACY_SEQUENCE_FIELD = "execution_graph"


class MissionSchemaError(ValueError):
    pass


@dataclass
class Mission:
    id: str
    version: int
    triggers: list[str] = field(default_factory=list)
    required_seats: list[dict] = field(default_factory=list)
    execution_sequence: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    completion: dict = field(default_factory=dict)
    # SHR-057: optional per-step timeout, keyed by step name. Missions
    # that omit this fall through to the compiler's default (600s).
    step_timeouts: dict = field(default_factory=dict)
    # SHR-058: optional per-step retry policy, keyed by step name. Shape:
    # {step_name: {"max_attempts": int >=1, "backoff": "none"|"fixed",
    #              "backoff_s"?: float >=0}}. Missing entry → supervisor
    # falls through to its own default retry budget.
    retry_policy: dict = field(default_factory=dict)
    # SHR-063: optional conservative per-step upper-bound projection used
    # for pre-flight budget gating. Shape: {step_name: {"tokens_in": int,
    # "tokens_out": int, "cost_usd": float}}. Missing entry → project
    # zero (see supervisor).
    step_budgets: dict = field(default_factory=dict)


def _read_sequence(data: dict) -> list:
    """Return the ordered step list, accepting the pre-SHR-009 field once."""
    has_new = SEQUENCE_FIELD in data
    has_legacy = LEGACY_SEQUENCE_FIELD in data
    if has_new and has_legacy:
        raise MissionSchemaError(
            f"declare {SEQUENCE_FIELD!r} or {LEGACY_SEQUENCE_FIELD!r}, not both"
        )
    if has_new:
        return data[SEQUENCE_FIELD]
    if has_legacy:
        warnings.warn(
            f"mission field {LEGACY_SEQUENCE_FIELD!r} is deprecated; "
            f"rename it to {SEQUENCE_FIELD!r} (SHR-009)",
            DeprecationWarning,
            stacklevel=3,
        )
        return data[LEGACY_SEQUENCE_FIELD]
    raise MissionSchemaError(f"missing field {SEQUENCE_FIELD!r}")


def validate(data: dict) -> Mission:
    if data.get("schema") != MISSION_SCHEMA:
        raise MissionSchemaError(
            f"expected schema {MISSION_SCHEMA!r}, got {data.get('schema')!r}"
        )
    sequence = _read_sequence(data)
    for k in ("id", "version", "required_seats",
              "required_outputs", "completion"):
        if k not in data:
            raise MissionSchemaError(f"missing field {k!r}")
    seats = data["required_seats"]
    if not isinstance(seats, list) or not seats:
        raise MissionSchemaError("required_seats must be a non-empty list")
    seat_ids: set[str] = set()
    for seat in seats:
        if not isinstance(seat, dict):
            raise MissionSchemaError("each seat must be a mapping")
        if "id" not in seat:
            raise MissionSchemaError("seat missing id")
        if seat["id"] in seat_ids:
            raise MissionSchemaError(f"duplicate seat id {seat['id']!r}")
        seat_ids.add(seat["id"])
        provides = seat.get("provides") or []
        if not isinstance(provides, list) or not provides:
            raise MissionSchemaError(
                f"seat {seat['id']!r} must declare non-empty provides[]"
            )
    if not isinstance(sequence, list) or not sequence:
        raise MissionSchemaError(f"{SEQUENCE_FIELD} must be non-empty")
    for step in sequence:
        if step not in seat_ids:
            raise MissionSchemaError(
                f"{SEQUENCE_FIELD} step {step!r} not in required_seats"
            )
    # Independence: referenced ids must exist.
    for seat in seats:
        indep = (seat.get("constraints") or {}).get("independent_from") or []
        for other in indep:
            if other not in seat_ids:
                raise MissionSchemaError(
                    f"seat {seat['id']!r} independent_from references "
                    f"unknown seat {other!r}"
                )
            if other == seat["id"]:
                raise MissionSchemaError(
                    f"seat {seat['id']!r} cannot be independent from itself"
                )
    step_timeouts = data.get("step_timeouts") or {}
    if not isinstance(step_timeouts, dict):
        raise MissionSchemaError("step_timeouts must be a mapping")
    for name, seconds in step_timeouts.items():
        if name not in sequence:
            raise MissionSchemaError(
                f"step_timeouts references unknown step {name!r}"
            )
        if not isinstance(seconds, int) or seconds <= 0:
            raise MissionSchemaError(
                f"step_timeouts[{name!r}] must be a positive integer"
            )
    retry_policy = data.get("retry_policy") or {}
    if not isinstance(retry_policy, dict):
        raise MissionSchemaError("retry_policy must be a mapping")
    for name, entry in retry_policy.items():
        if name not in sequence:
            raise MissionSchemaError(
                f"retry_policy references unknown step {name!r}"
            )
        if not isinstance(entry, dict):
            raise MissionSchemaError(
                f"retry_policy[{name!r}] must be a mapping"
            )
        attempts = entry.get("max_attempts")
        if not isinstance(attempts, int) or attempts < 1:
            raise MissionSchemaError(
                f"retry_policy[{name!r}].max_attempts must be a positive integer"
            )
        backoff = entry.get("backoff", "none")
        if backoff not in ("none", "fixed"):
            raise MissionSchemaError(
                f"retry_policy[{name!r}].backoff must be 'none' or 'fixed'"
            )
        if backoff == "fixed":
            secs = entry.get("backoff_s", 0)
            if not isinstance(secs, (int, float)) or secs < 0:
                raise MissionSchemaError(
                    f"retry_policy[{name!r}].backoff_s must be non-negative"
                )
    step_budgets = data.get("step_budgets") or {}
    if not isinstance(step_budgets, dict):
        raise MissionSchemaError("step_budgets must be a mapping")
    for name, entry in step_budgets.items():
        if name not in sequence:
            raise MissionSchemaError(
                f"step_budgets references unknown step {name!r}"
            )
        if not isinstance(entry, dict):
            raise MissionSchemaError(
                f"step_budgets[{name!r}] must be a mapping"
            )
        for k in ("tokens_in", "tokens_out", "cost_usd"):
            v = entry.get(k, 0)
            if not isinstance(v, (int, float)) or v < 0:
                raise MissionSchemaError(
                    f"step_budgets[{name!r}].{k} must be non-negative"
                )
    return Mission(
        id=str(data["id"]),
        version=int(data["version"]),
        triggers=list(data.get("triggers") or []),
        required_seats=list(seats),
        execution_sequence=list(sequence),
        required_outputs=list(data["required_outputs"]),
        completion=dict(data["completion"]),
        step_timeouts=dict(step_timeouts),
        retry_policy=dict(retry_policy),
        step_budgets=dict(step_budgets),
    )
