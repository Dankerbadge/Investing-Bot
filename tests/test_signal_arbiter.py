from investing_bot.models import Candidate
from investing_bot.signal_arbiter import arbitrate_signals, selected_candidates


def _candidate(ticker: str, underlying: str, event_window: str, alpha_lcb: float, spread_cost: float = 0.01) -> Candidate:
    return Candidate(
        ticker=ticker,
        underlying=underlying,
        event_key=event_window,
        strategy_family="post_event_iv",
        side="sell",
        reference_price=1.0,
        surface_residual=alpha_lcb,
        convergence_probability=0.60,
        fill_probability=0.70,
        spread_cost=spread_cost,
        hedge_cost=0.005,
        stale_quote_penalty=0.001,
        event_gap_penalty=0.001,
        capital_lockup_penalty=0.001,
        confidence=0.70,
        book_depth_contracts=120,
        quote_age_seconds=0.5,
        payoff_multiple=1.2,
        loss_multiple=1.0,
        metadata={
            "event_window": event_window,
            "alpha_density_lcb": alpha_lcb,
            "assignment_risk": 0.10,
            "capital_usage_score": 0.05,
        },
    )


def test_arbiter_enforces_one_thesis_per_underlying_event_window():
    candidates = [
        _candidate("SPY-A", "SPY", "earnings_window", 0.020),
        _candidate("SPY-B", "SPY", "earnings_window", 0.010),
        _candidate("QQQ-A", "QQQ", "earnings_window", 0.015),
    ]

    result = arbitrate_signals(candidates, max_per_thesis=1)
    selected = selected_candidates(result)

    assert len(selected) == 2
    assert {row.ticker for row in selected} == {"SPY-A", "QQQ-A"}
    assert len(result.dropped) == 1


def test_arbiter_keeps_multiple_windows_for_same_underlying():
    candidates = [
        _candidate("SPY-AM", "SPY", "morning_window", 0.012),
        _candidate("SPY-PM", "SPY", "afternoon_window", 0.011),
    ]

    result = arbitrate_signals(candidates, max_per_thesis=1)
    selected = selected_candidates(result)

    assert len(selected) == 2
    assert {row.event_key for row in selected} == {"morning_window", "afternoon_window"}
