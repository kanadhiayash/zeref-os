"""Reasoning-class routing for execution tasks."""

from __future__ import annotations

from enum import Enum

from shiroe.execution.criticality import RiskLevel


class ReasoningClass(str, Enum):
    fast = "fast"
    balanced = "balanced"
    deep = "deep"
    frontier = "frontier"


_MAP = {
    RiskLevel.low: ReasoningClass.fast,
    RiskLevel.medium: ReasoningClass.balanced,
    RiskLevel.high: ReasoningClass.deep,
    RiskLevel.critical: ReasoningClass.frontier,
}
_ORDER = (
    ReasoningClass.fast,
    ReasoningClass.balanced,
    ReasoningClass.deep,
    ReasoningClass.frontier,
)


def resolve_class(risk: RiskLevel | str) -> ReasoningClass:
    level = risk if isinstance(risk, RiskLevel) else RiskLevel(str(risk).lower())
    return _MAP[level]


def validate_request(risk: RiskLevel | str, requested: ReasoningClass | str) -> ReasoningClass:
    entitled = resolve_class(risk)
    requested_class = ReasoningClass(requested)
    if _ORDER.index(requested_class) > _ORDER.index(entitled):
        level = risk if isinstance(risk, RiskLevel) else RiskLevel(str(risk).lower())
        raise ValueError(
            f"{level.value} entitles at most {entitled.value}; "
            f"{requested_class.value} denied (frontier is critical-only)"
        )
    return requested_class
