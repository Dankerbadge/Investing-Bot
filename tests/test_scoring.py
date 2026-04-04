from investing_bot.gating import LiquidityGate, evaluate_liquidity
from investing_bot.models import Candidate
from investing_bot.scoring import compute_net_executable_edge
from investing_bot.sizing import fractional_kelly_fraction, full_kelly_fraction


def _candidate(**overrides):
    base = dict(
        ticker="SPY-TEST",
        underlying="SPY",
        event_key="event-1",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.04,
        convergence_probability=0.70,
        fill_probability=0.80,
        spread_cost=0.005,
        hedge_cost=0.002,
        stale_quote_penalty=0.001,
        event_gap_penalty=0.003,
        capital_lockup_penalty=0.002,
        confidence=0.70,
        book_depth_contracts=50,
        quote_age_seconds=1.0,
        payoff_multiple=1.0,
        loss_multiple=1.0,
    )
    base.update(overrides)
    return Candidate(**base)


def test_net_executable_edge_formula():
    candidate = _candidate()
    edge = compute_net_executable_edge(candidate)
    # (0.04 * 0.70 * 0.80) - (0.005 + 0.002 + 0.001 + 0.003 + 0.002) = 0.0094
    assert round(edge, 6) == 0.0094


def test_kelly_fraction_math():
    full = full_kelly_fraction(win_probability=0.60, payoff_multiple=1.0, loss_multiple=1.0)
    used = fractional_kelly_fraction(kelly_full=full, kelly_fraction=0.25, max_fraction=0.10)
    assert round(full, 6) == 0.2
    assert round(used, 6) == 0.05


def test_liquidity_gate_fails_stale_quote_and_spread():
    candidate = _candidate(quote_age_seconds=9.0, spread_cost=0.08)
    passed, reasons = evaluate_liquidity(candidate, LiquidityGate(max_quote_age_seconds=3.0, max_spread_cost=0.03))
    assert passed is False
    assert "quote_stale" in reasons
    assert "spread_too_wide" in reasons
