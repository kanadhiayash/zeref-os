import pytest

from shiroe.execution.criticality import RiskLevel, classify_node
from shiroe.execution.reasoning import ReasoningClass, resolve_class, validate_request
from shiroe.work.schema import NodeKind, WorkNode


def test_classify_node_uses_highest_structured_signal():
    node = WorkNode(
        id="n",
        graph_id="g",
        kind=NodeKind.task,
        objective="publish",
        risk="critical",
    )
    assert classify_node(node) is RiskLevel.critical


def test_reasoning_class_mapping_is_provider_neutral():
    assert resolve_class(RiskLevel.low) is ReasoningClass.fast
    assert resolve_class(RiskLevel.medium) is ReasoningClass.balanced
    assert resolve_class(RiskLevel.high) is ReasoningClass.deep
    assert resolve_class(RiskLevel.critical) is ReasoningClass.frontier


def test_frontier_is_critical_only():
    with pytest.raises(ValueError, match="frontier"):
        validate_request(RiskLevel.high, ReasoningClass.frontier)
