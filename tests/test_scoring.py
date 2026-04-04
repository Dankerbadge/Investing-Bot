from investing_bot.gating import LiquidityGate, evaluate_liquidity
from investing_bot.models import Candidate
from investing_bot.scoring import ExecutionAdjustments, compute_net_executable_edge
from investing_bot.sizing import (
    dynamic_fractional_kelly_fraction,
    fractional_kelly_fraction,
    full_kelly_fraction,
)


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


def test_contract_hygiene_filters_adjusted_and_nonstandard():
    candidate = _candidate(
        metadata={
            "is_adjusted_option": True,
            "is_nonstandard_expiration": True,
            "quote_locked_or_crossed": True,
        }
    )
    passed, reasons = evaluate_liquidity(candidate, LiquidityGate())
    assert passed is False
    assert "adjusted_option_excluded" in reasons
    assert "nonstandard_expiration_excluded" in reasons
    assert "locked_or_crossed_market" in reasons


def test_adjusted_edge_haircut_reduces_edge():
    candidate = _candidate()
    raw = compute_net_executable_edge(candidate)
    adjusted = compute_net_executable_edge(
        candidate,
        ExecutionAdjustments(
            slippage_p95_penalty=0.002,
            post_fill_alpha_decay_penalty=0.001,
            uncertainty_penalty=0.001,
        ),
    )
    assert adjusted < raw


def test_dynamic_kelly_scales_down_in_bad_regime():
    full = full_kelly_fraction(win_probability=0.60, payoff_multiple=1.0, loss_multiple=1.0)
    baseline = dynamic_fractional_kelly_fraction(
        kelly_full=full,
        base_kelly_fraction=0.25,
        confidence=0.9,
        drawdown_fraction=0.0,
        model_error_score=0.0,
        spread_regime_penalty=0.0,
        slippage_penalty=0.0,
        max_fraction=0.10,
    )
    stressed = dynamic_fractional_kelly_fraction(
        kelly_full=full,
        base_kelly_fraction=0.25,
        confidence=0.5,
        drawdown_fraction=0.2,
        model_error_score=0.4,
        spread_regime_penalty=0.3,
        slippage_penalty=0.2,
        max_fraction=0.10,
    )
    assert stressed < baseline
