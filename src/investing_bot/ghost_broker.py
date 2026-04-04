from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GhostExecutionResult:
    simulated_fill_quantity: int
    simulated_fill_probability: float
    expected_slippage_dollars: float
    should_cancel_replace: bool


def simulate_passive_limit_fill(
    *,
    order_quantity: int,
    best_bid: float,
    best_ask: float,
    visible_depth_contracts: int,
    urgency: float = 0.5,
    random_seed: int = 0,
) -> GhostExecutionResult:
    if order_quantity <= 0:
        raise ValueError("order_quantity must be positive")
    if best_ask <= best_bid:
        raise ValueError("best_ask must be greater than best_bid")

    spread = best_ask - best_bid
    depth_ratio = min(1.0, visible_depth_contracts / float(max(order_quantity, 1)))
    urgency_clamped = min(1.0, max(0.0, urgency))

    # Simple but useful baseline model for executable-quality simulation.
    fill_probability = max(0.0, min(1.0, 0.85 * depth_ratio - 2.0 * spread - 0.25 * urgency_clamped + 0.2))
    expected_slippage = round(spread * (0.5 + urgency_clamped), 4)

    rng = random.Random(random_seed)
    if rng.random() <= fill_probability:
        simulated_fill = order_quantity
    else:
        simulated_fill = int(order_quantity * fill_probability)

    should_cancel_replace = simulated_fill < order_quantity and fill_probability < 0.55

    return GhostExecutionResult(
        simulated_fill_quantity=max(0, simulated_fill),
        simulated_fill_probability=round(fill_probability, 6),
        expected_slippage_dollars=expected_slippage,
        should_cancel_replace=should_cancel_replace,
    )
