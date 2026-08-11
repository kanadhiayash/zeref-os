"""Provider-neutral execution criticality primitives."""

from __future__ import annotations

from enum import Enum

from shiroe.work.schema import NodeKind, WorkNode


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


_RISK_ORDER = (RiskLevel.low, RiskLevel.medium, RiskLevel.high, RiskLevel.critical)


def _max_risk(*levels: RiskLevel) -> RiskLevel:
    return max(levels, key=_RISK_ORDER.index)


def classify_node(node: WorkNode) -> RiskLevel:
    try:
        explicit = RiskLevel(str(node.risk).lower())
    except ValueError:
        explicit = RiskLevel.medium
    structural = RiskLevel.low
    if node.kind is NodeKind.approval or node.approval_required:
        structural = _max_risk(structural, RiskLevel.high)
    if node.evidence_required or node.independent_review:
        structural = _max_risk(structural, RiskLevel.medium)
    if node.metadata.get("destructive") or node.metadata.get("external_write"):
        structural = _max_risk(structural, RiskLevel.critical)
    return _max_risk(explicit, structural)
