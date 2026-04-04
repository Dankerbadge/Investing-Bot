from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GhostExecutionResult:
    simulated_fill_quantity: int
    simulated_fill_probability: float
    filled_ratio: float
    expected_slippage_dollars: float
    adverse_selection_penalty: float
    post_fill_alpha_decay_penalty: float
    estimated_total_execution_penalty: float
    should_cancel_replace: bool


def simulate_passive_limit_fill(
    *,
    order_quantity: int,
    best_bid: float,
    best_ask: float,
    visible_depth_contracts: int,
    queue_ahead_contracts: int = 0,
    urgency: float = 0.5,
    wait_time_seconds: float = 15.0,
    market_phase: str = "continuous",
    random_seed: int = 0,
) -> GhostExecutionResult:
    """
    A harsher passive-fill simulator:
    - partial fills by queue/depth imbalance
    - wait-time driven alpha decay
    - adverse selection penalty that rises with urgency and wide spreads
    - cancel/replace trigger when expected fill quality is poor
    """

    if order_quantity <= 0:
        raise ValueError("order_quantity must be positive")
    if best_ask <= best_bid:
        raise ValueError("best_ask must be greater than best_bid")

    spread = best_ask - best_bid
    depth_ratio = min(1.0, visible_depth_contracts / float(max(order_quantity, 1)))
    queue_penalty = min(1.0, max(0.0, queue_ahead_contracts / float(max(order_quantity, 1))))
    urgency_clamped = min(1.0, max(0.0, urgency))
    wait_penalty = min(1.0, max(0.0, wait_time_seconds / 90.0))

    phase_multiplier = {
        "open": 0.85,
        "close": 0.90,
        "event": 0.80,
        "continuous": 1.00,
    }.get(str(market_phase or "").strip().lower(), 1.00)

    base_fill_probability = (
        0.75 * depth_ratio
        - 0.20 * queue_penalty
        - 1.75 * spread
        - 0.20 * urgency_clamped
        - 0.12 * wait_penalty
        + 0.25
    )
    fill_probability = min(1.0, max(0.0, base_fill_probability * phase_multiplier))

    expected_slippage = max(0.0, spread * (0.35 + urgency_clamped + 0.25 * wait_penalty))
    adverse_selection_penalty = max(0.0, spread * (0.15 + 0.65 * urgency_clamped))
    post_fill_alpha_decay_penalty = max(0.0, 0.01 * wait_penalty + 0.005 * queue_penalty)

    rng = random.Random(random_seed)
    realized_fill_ratio = fill_probability * (0.65 + 0.35 * rng.random())
    simulated_fill = int(round(order_quantity * realized_fill_ratio))
    simulated_fill = min(order_quantity, max(0, simulated_fill))

    should_cancel_replace = (
        simulated_fill < order_quantity
        and fill_probability < 0.55
        and (spread > 0.03 or wait_penalty > 0.35)
    )

    total_penalty = expected_slippage + adverse_selection_penalty + post_fill_alpha_decay_penalty

    return GhostExecutionResult(
        simulated_fill_quantity=simulated_fill,
        simulated_fill_probability=round(fill_probability, 6),
        filled_ratio=round(simulated_fill / float(order_quantity), 6),
        expected_slippage_dollars=round(expected_slippage, 6),
        adverse_selection_penalty=round(adverse_selection_penalty, 6),
        post_fill_alpha_decay_penalty=round(post_fill_alpha_decay_penalty, 6),
        estimated_total_execution_penalty=round(total_penalty, 6),
        should_cancel_replace=should_cancel_replace,
    )
