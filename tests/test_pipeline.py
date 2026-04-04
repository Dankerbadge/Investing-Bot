from investing_bot.gating import LiquidityGate
from investing_bot.models import Candidate
from investing_bot.pipeline import build_trade_plan
from investing_bot.risk import ConcentrationLimits


def _candidate(ticker: str, underlying: str, event_key: str, edge_residual: float, fill_prob: float = 0.72):
    return Candidate(
        ticker=ticker,
        underlying=underlying,
        event_key=event_key,
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=edge_residual,
        convergence_probability=0.64,
        fill_probability=fill_prob,
        spread_cost=0.007,
        hedge_cost=0.004,
        stale_quote_penalty=0.001,
        event_gap_penalty=0.002,
        capital_lockup_penalty=0.002,
        confidence=0.70,
        book_depth_contracts=80,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
    )


def test_pipeline_prefers_concentrated_unique_underlyings():
    candidates = [
        _candidate("SPY-A", "SPY", "event-1", 0.065),
        _candidate("SPY-B", "SPY", "event-2", 0.060),
        _candidate("QQQ-A", "QQQ", "event-3", 0.058),
        _candidate("IWM-A", "IWM", "event-4", 0.054),
    ]

    result = build_trade_plan(
        candidates=candidates,
        bankroll=10000,
        gate=LiquidityGate(),
        limits=ConcentrationLimits(max_open_positions=2, max_per_underlying=1, max_per_event=1),
    )

    selected = result["selected"]
    assert len(selected) == 2
    assert len({row["underlying"] for row in selected}) == 2


def test_pipeline_allows_zero_positions_when_no_positive_edge():
    candidates = [_candidate("SPY-A", "SPY", "event-1", 0.01, fill_prob=0.4)]

    result = build_trade_plan(
        candidates=candidates,
        bankroll=10000,
        gate=LiquidityGate(),
        limits=ConcentrationLimits(),
    )

    assert result["selected_count"] == 0


def test_pipeline_ranks_by_alpha_density_not_raw_edge():
    slow_high_edge = _candidate("SPY-SLOW", "SPY", "event-1", 0.08)
    fast_lower_edge = _candidate("QQQ-FAST", "QQQ", "event-2", 0.06)

    slow_high_edge.metadata["expected_holding_minutes"] = 1440
    fast_lower_edge.metadata["expected_holding_minutes"] = 30

    result = build_trade_plan(
        candidates=[slow_high_edge, fast_lower_edge],
        bankroll=10000,
        gate=LiquidityGate(),
        limits=ConcentrationLimits(max_open_positions=1, max_per_underlying=1, max_per_event=1),
    )

    assert result["selected_count"] == 1
    assert result["selected"][0]["ticker"] == "QQQ-FAST"
