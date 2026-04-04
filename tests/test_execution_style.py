from investing_bot.execution_style import choose_execution_style
from investing_bot.models import Candidate


def _candidate(**overrides):
    base = dict(
        ticker="SPY-TEST",
        underlying="SPY",
        event_key="event-1",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.06,
        convergence_probability=0.65,
        fill_probability=0.7,
        spread_cost=0.02,
        hedge_cost=0.003,
        stale_quote_penalty=0.001,
        event_gap_penalty=0.002,
        capital_lockup_penalty=0.002,
        confidence=0.7,
        book_depth_contracts=100,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
        metadata={},
    )
    base.update(overrides)
    return Candidate(**base)


def test_execution_style_penalty_increases_with_budget_pressure():
    candidate = _candidate(spread_cost=0.03, fill_probability=0.6)
    low = choose_execution_style(
        candidate=candidate,
        adjusted_edge=0.02,
        recent_order_requests_per_minute=10,
        order_request_budget_per_minute=120,
    )
    high = choose_execution_style(
        candidate=candidate,
        adjusted_edge=0.02,
        recent_order_requests_per_minute=110,
        order_request_budget_per_minute=120,
    )

    assert high.style in {"passive_touch", "cross_now"}
    assert low.style in {"synthetic_ladder", "native_walk_limit", "passive_improve", "passive_touch"}


def test_native_walk_limit_selected_when_supported():
    candidate = _candidate(
        spread_cost=0.04,
        fill_probability=0.55,
        metadata={
            "supports_native_walk_limit": True,
            "native_walk_limit_api_verified": True,
            "native_walk_confirmed_uses": 30,
            "native_walk_alpha_density_lcb": 0.001,
            "deployment_stage": "scaled_1",
            "is_stock_etf_option": True,
            "is_regular_trading_hours": True,
            "allow_native_walk_limit": True,
            "quote_mode": "realtime",
        },
    )
    decision = choose_execution_style(
        candidate=candidate,
        adjusted_edge=0.03,
        recent_order_requests_per_minute=20,
        order_request_budget_per_minute=120,
    )
    assert decision.style == "native_walk_limit"
    assert decision.expected_replace_count == 1


def test_synthetic_ladder_used_when_native_unavailable():
    candidate = _candidate(
        spread_cost=0.04,
        fill_probability=0.55,
        metadata={
            "supports_native_walk_limit": False,
            "allow_synthetic_ladder": True,
        },
    )
    decision = choose_execution_style(
        candidate=candidate,
        adjusted_edge=0.03,
        recent_order_requests_per_minute=20,
        order_request_budget_per_minute=120,
    )
    assert decision.style == "synthetic_ladder"
    assert decision.expected_replace_count >= 3


def test_native_walk_limit_requires_api_verification():
    candidate = _candidate(
        spread_cost=0.04,
        fill_probability=0.55,
        metadata={
            "supports_native_walk_limit": True,
            "native_walk_limit_api_verified": False,
            "allow_synthetic_ladder": True,
        },
    )
    decision = choose_execution_style(
        candidate=candidate,
        adjusted_edge=0.03,
        recent_order_requests_per_minute=20,
        order_request_budget_per_minute=120,
    )
    assert decision.style == "synthetic_ladder"
