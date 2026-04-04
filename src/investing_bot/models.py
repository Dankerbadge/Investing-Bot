from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Candidate:
    ticker: str
    underlying: str
    event_key: str
    strategy_family: str
    side: str
    reference_price: float
    surface_residual: float
    convergence_probability: float
    fill_probability: float
    spread_cost: float
    hedge_cost: float
    stale_quote_penalty: float
    event_gap_penalty: float
    capital_lockup_penalty: float
    confidence: float
    book_depth_contracts: int
    quote_age_seconds: float
    payoff_multiple: float
    loss_multiple: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: Candidate
    net_edge: float
    executable: bool
    gate_reasons: tuple[str, ...]
    kelly_full: float
    kelly_used: float
    target_notional: float
    raw_net_edge: float = 0.0
    expected_fill_probability: float = 0.0
    slippage_p95_penalty: float = 0.0
    post_fill_alpha_decay_penalty: float = 0.0
    uncertainty_penalty: float = 0.0
    execution_penalty: float = 0.0
    model_error_score: float = 0.0
    alpha_density: float = 0.0
    execution_style: str = "passive_touch"
    policy_action: str = "trade"
    deployment_stage: str = "scaled"
    expected_replace_count: int = 0
    live_prior_cap_penalty: float = 0.0
    request_budget_penalty: float = 0.0
    cancel_replace_race_penalty: float = 0.0
    drift_kelly_multiplier: float = 1.0
    stage_capital_multiplier: float = 1.0
    deployment_capital_multiplier: float = 1.0
    effective_capital_multiplier: float = 1.0
    latency_penalty: float = 0.0
    risk_penalty: float = 0.0
    execution_adjusted_edge: float = 0.0
    style_adjusted_edge: float = 0.0
    risk_adjusted_edge: float = 0.0


@dataclass(frozen=True)
class SelectedTrade:
    ticker: str
    underlying: str
    event_key: str
    strategy_family: str
    side: str
    net_edge: float
    kelly_used: float
    target_notional: float
    confidence: float
    raw_net_edge: float = 0.0
    alpha_density: float = 0.0
    execution_style: str = "passive_touch"
