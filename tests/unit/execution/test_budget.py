from shiroe.execution.budget import BudgetTracker


def test_budget_projection_blocks_before_crossing_limit():
    budget = BudgetTracker(usd_max=1.0, tokens_input_max=100, tokens_output_max=100)
    assert budget.would_exceed({"cost_usd": 1.01}) == "usd_max"
    assert budget.snapshot()["usage_totals"]["cost_usd"] == 0.0


def test_budget_charge_records_usage():
    budget = BudgetTracker(usd_max=1.0, tokens_input_max=100, tokens_output_max=100)
    budget.charge(usd=0.5, tokens_input=10, tokens_output=20)
    snap = budget.snapshot()
    assert snap["usage_totals"] == {"cost_usd": 0.5, "tokens_in": 10, "tokens_out": 20}
