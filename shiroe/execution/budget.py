"""Per-run cost and token budget tracking."""

from __future__ import annotations

from dataclasses import dataclass


class BudgetError(RuntimeError):
    pass


@dataclass
class BudgetTracker:
    usd_max: float = 0.0
    tokens_input_max: int = 0
    tokens_output_max: int = 0
    usd_spent: float = 0.0
    tokens_input_spent: int = 0
    tokens_output_spent: int = 0

    def would_exceed(self, projection: dict) -> str | None:
        cost = float(projection.get("cost_usd", 0.0) or 0.0)
        tokens_in = int(projection.get("tokens_in", 0) or 0)
        tokens_out = int(projection.get("tokens_out", 0) or 0)
        if self.usd_max and self.usd_spent + cost > self.usd_max:
            return "usd_max"
        if self.tokens_input_max and self.tokens_input_spent + tokens_in > self.tokens_input_max:
            return "tokens_input_max"
        if self.tokens_output_max and self.tokens_output_spent + tokens_out > self.tokens_output_max:
            return "tokens_output_max"
        return None

    def charge(
        self,
        *,
        usd: float = 0.0,
        tokens_input: int = 0,
        tokens_output: int = 0,
    ) -> None:
        self.usd_spent += usd
        self.tokens_input_spent += tokens_input
        self.tokens_output_spent += tokens_output

    def snapshot(self) -> dict:
        return {
            "usd_spent": round(self.usd_spent, 4),
            "tokens_input_spent": self.tokens_input_spent,
            "tokens_output_spent": self.tokens_output_spent,
            "usage_totals": {
                "cost_usd": round(self.usd_spent, 6),
                "tokens_in": self.tokens_input_spent,
                "tokens_out": self.tokens_output_spent,
            },
        }
