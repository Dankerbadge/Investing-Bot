from __future__ import annotations

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class GhostExecutionResult:
    execution_style: str
    simulated_fill_quantity: int
    simulated_fill_probability: float
    filled_ratio: float
    expected_slippage_dollars: float
    adverse_selection_penalty: float
    post_fill_alpha_decay_penalty: float
    request_budget_penalty: float
    cancel_replace_race_penalty: float
    estimated_total_execution_penalty: float
    should_cancel_replace: bool
    walk_steps_used: int


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
    execution_style: str = "passive_touch",
    walk_step_seconds: float = 5.0,
    max_walk_steps: int = 4,
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

    style = str(execution_style or "").strip().lower() or "passive_touch"
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
    request_budget_penalty = 0.0
    cancel_replace_race_penalty = 0.0
    walk_steps_used = 0

    if style == "cross_now":
        fill_probability = max(fill_probability, 0.98)
        expected_slippage = max(expected_slippage, spread * 0.95)
        adverse_selection_penalty += spread * 0.05
    elif style == "passive_improve":
        fill_probability = min(1.0, fill_probability + 0.05)
        expected_slippage = max(0.0, expected_slippage - spread * 0.08)
        request_budget_penalty += 0.0015
        cancel_replace_race_penalty += 0.0008
    elif style == "native_walk_limit":
        walk_steps_used = max(0, min(10, int(max_walk_steps)))
        step_seconds = min(60.0, max(2.0, float(walk_step_seconds)))
        cadence_penalty = 0.0002 * max(0.0, (10.0 - step_seconds))
        fill_probability = min(1.0, fill_probability + min(0.20, walk_steps_used * 0.022))
        expected_slippage += spread * (0.08 + 0.01 * walk_steps_used)
        request_budget_penalty += 0.001 + cadence_penalty
        cancel_replace_race_penalty += 0.0015 + cadence_penalty
    elif style == "synthetic_ladder":
        walk_steps_used = max(0, min(10, int(max_walk_steps)))
        fill_probability = min(1.0, fill_probability + min(0.16, walk_steps_used * 0.018))
        expected_slippage += spread * (0.12 + 0.012 * walk_steps_used)
        request_budget_penalty += 0.003 + (0.0012 * walk_steps_used)
        cancel_replace_race_penalty += 0.002 + (0.001 * walk_steps_used)

    rng = random.Random(random_seed)
    realized_fill_ratio = fill_probability * (0.65 + 0.35 * rng.random())
    simulated_fill = int(round(order_quantity * realized_fill_ratio))
    simulated_fill = min(order_quantity, max(0, simulated_fill))

    should_cancel_replace = (
        style in {"passive_touch", "passive_improve", "synthetic_ladder"}
        and
        simulated_fill < order_quantity
        and fill_probability < 0.55
        and (spread > 0.03 or wait_penalty > 0.35)
    )

    total_penalty = (
        expected_slippage
        + adverse_selection_penalty
        + post_fill_alpha_decay_penalty
        + request_budget_penalty
        + cancel_replace_race_penalty
    )

    return GhostExecutionResult(
        execution_style=style,
        simulated_fill_quantity=simulated_fill,
        simulated_fill_probability=round(fill_probability, 6),
        filled_ratio=round(simulated_fill / float(order_quantity), 6),
        expected_slippage_dollars=round(expected_slippage, 6),
        adverse_selection_penalty=round(adverse_selection_penalty, 6),
        post_fill_alpha_decay_penalty=round(post_fill_alpha_decay_penalty, 6),
        request_budget_penalty=round(request_budget_penalty, 6),
        cancel_replace_race_penalty=round(cancel_replace_race_penalty, 6),
        estimated_total_execution_penalty=round(total_penalty, 6),
        should_cancel_replace=should_cancel_replace,
        walk_steps_used=walk_steps_used,
    )
