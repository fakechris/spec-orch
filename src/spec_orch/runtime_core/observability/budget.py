from __future__ import annotations

from spec_orch.runtime_core.observability.models import RuntimeBudgetVisibility


def build_budget_visibility(
    *,
    budget_key: str,
    planned_steps: int,
    completed_steps: int,
    loop_budget: int = 0,
    remaining_loop_budget: int = 0,
    continuation_count: int = 0,
    recent_token_growth: int = 0,
) -> RuntimeBudgetVisibility:
    justified = remaining_loop_budget > 0 or completed_steps < planned_steps
    return RuntimeBudgetVisibility(
        budget_key=budget_key,
        planned_steps=planned_steps,
        completed_steps=completed_steps,
        remaining_steps=max(0, planned_steps - completed_steps),
        loop_budget=max(0, loop_budget),
        remaining_loop_budget=max(0, remaining_loop_budget),
        continuation_count=max(0, continuation_count),
        recent_token_growth=max(0, recent_token_growth),
        justified=justified,
    )


__all__ = ["build_budget_visibility"]
