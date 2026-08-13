"""H2.1: pin BudgetTracker None-vs-0 semantics and validation."""

from __future__ import annotations

import pytest

from shiroe.execution.budget import BudgetTracker


def test_default_construction_is_unlimited_on_every_axis():
    b = BudgetTracker()
    assert b.would_exceed({"cost_usd": 1_000_000, "tokens_in": 1_000_000, "tokens_out": 1_000_000}) is None


def test_zero_cap_means_unlimited_for_each_axis_independently():
    b = BudgetTracker(usd_max=10.0, tokens_input_max=0, tokens_output_max=0)
    assert b.would_exceed({"tokens_in": 9_999_999, "tokens_out": 9_999_999}) is None


def test_positive_cap_allows_reaching_exactly_the_cap():
    b = BudgetTracker(usd_max=1.0)
    assert b.would_exceed({"cost_usd": 1.0}) is None
    b.charge(usd=1.0)
    assert b.would_exceed({}) is None


def test_positive_cap_bursts_when_projection_exceeds():
    b = BudgetTracker(usd_max=1.0, tokens_input_max=100, tokens_output_max=100)
    assert b.would_exceed({"cost_usd": 1.01}) == "usd_max"
    assert b.would_exceed({"tokens_in": 101}) == "tokens_input_max"
    assert b.would_exceed({"tokens_out": 101}) == "tokens_output_max"


def test_usd_max_burst_first_axis_wins():
    b = BudgetTracker(usd_max=1.0, tokens_input_max=1, tokens_output_max=1)
    assert b.would_exceed({"cost_usd": 2, "tokens_in": 2, "tokens_out": 2}) == "usd_max"


def test_charge_accumulates_across_calls():
    b = BudgetTracker(usd_max=10.0)
    b.charge(usd=3.0)
    b.charge(usd=4.0)
    snap = b.snapshot()
    assert snap["usd_spent"] == 7.0


def test_snapshot_rounds_usd_to_four_decimal_places_in_top_level():
    b = BudgetTracker()
    b.charge(usd=1.234567)
    snap = b.snapshot()
    assert snap["usd_spent"] == 1.2346


def test_snapshot_usage_totals_rounds_to_six_decimal_places():
    b = BudgetTracker()
    b.charge(usd=1.2345678)
    snap = b.snapshot()
    assert snap["usage_totals"]["cost_usd"] == 1.234568


@pytest.mark.parametrize(
    "kwargs",
    [
        {"usd_max": -0.01},
        {"tokens_input_max": -1},
        {"tokens_output_max": -1},
    ],
)
def test_negative_cap_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        BudgetTracker(**kwargs)


def test_none_is_not_a_valid_cap_input():
    with pytest.raises(TypeError):
        BudgetTracker(usd_max=None)  # type: ignore[arg-type]
