"""Per-run cost + token budget tracker."""

from __future__ import annotations

from dataclasses import dataclass


class BudgetError(RuntimeError):
    pass


@dataclass
class BudgetTracker:
    usd_max: float
    tokens_input_max: int
    tokens_output_max: int
    usd_spent: float = 0.0
    tokens_input_spent: int = 0
    tokens_output_spent: int = 0

    def charge(self, *, usd: float = 0.0,
               tokens_input: int = 0,
               tokens_output: int = 0) -> None:
        self.usd_spent += usd
        self.tokens_input_spent += tokens_input
        self.tokens_output_spent += tokens_output

    def exceeded(self) -> str | None:
        if self.usd_max and self.usd_spent > self.usd_max:
            return f"usd_max exceeded: {self.usd_spent:.2f} > {self.usd_max:.2f}"
        if self.tokens_input_max and self.tokens_input_spent > self.tokens_input_max:
            return (f"tokens_input_max exceeded: "
                    f"{self.tokens_input_spent} > {self.tokens_input_max}")
        if self.tokens_output_max and self.tokens_output_spent > self.tokens_output_max:
            return (f"tokens_output_max exceeded: "
                    f"{self.tokens_output_spent} > {self.tokens_output_max}")
        return None

    def would_exceed(self, projection: dict) -> str | None:
        """Return the name of the field a projected step charge would burst.

        SHR-063: called before invoking a step to gate against a
        conservative upper-bound estimate. Missing keys default to 0 —
        an adapter that doesn't declare projection doesn't get to skip
        the check by silence.
        """
        p_cost = float(projection.get("cost_usd", 0.0) or 0.0)
        p_in = int(projection.get("tokens_in", 0) or 0)
        p_out = int(projection.get("tokens_out", 0) or 0)
        if self.usd_max and self.usd_spent + p_cost > self.usd_max:
            return (f"usd_max would exceed: "
                    f"{self.usd_spent + p_cost:.2f} > {self.usd_max:.2f}")
        if self.tokens_input_max and self.tokens_input_spent + p_in > self.tokens_input_max:
            return (f"tokens_input_max would exceed: "
                    f"{self.tokens_input_spent + p_in} > {self.tokens_input_max}")
        if self.tokens_output_max and self.tokens_output_spent + p_out > self.tokens_output_max:
            return (f"tokens_output_max would exceed: "
                    f"{self.tokens_output_spent + p_out} > {self.tokens_output_max}")
        return None

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
