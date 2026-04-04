from investing_bot.allocator import (
    AllocationConstraints,
    apply_greeks_overlay,
    optimize_basket,
    score_incremental_capital_efficiency,
)
from investing_bot.models import Candidate, ScoredCandidate


def _scored(
    ticker: str,
    *,
    edge: float,
    target: float,
    alpha_density: float,
    delta_per_notional: float = 0.0,
    vega_per_notional: float = 0.0,
) -> ScoredCandidate:
    candidate = Candidate(
        ticker=ticker,
        underlying=ticker.split("-")[0],
        event_key=f"{ticker}-evt",
        strategy_family="iv_repricing",
        side="sell",
        reference_price=1.0,
        surface_residual=0.05,
        convergence_probability=0.6,
        fill_probability=0.7,
        spread_cost=0.01,
        hedge_cost=0.01,
        stale_quote_penalty=0.0,
        event_gap_penalty=0.0,
        capital_lockup_penalty=0.0,
        confidence=0.7,
        book_depth_contracts=100,
        quote_age_seconds=1.0,
        payoff_multiple=1.2,
        loss_multiple=1.0,
        metadata={
            "expected_holding_minutes": 30,
            "delta_per_notional": delta_per_notional,
            "vega_per_notional": vega_per_notional,
        },
    )
    return ScoredCandidate(
        candidate=candidate,
        net_edge=edge,
        executable=True,
        gate_reasons=(),
        kelly_full=0.2,
        kelly_used=0.05,
        target_notional=target,
        expected_fill_probability=0.7,
        alpha_density=alpha_density,
        execution_style="passive_touch",
    )


def test_allocator_respects_delta_caps_and_selects_best_names():
    rows = [
        _scored("SPY-A", edge=0.02, target=500, alpha_density=0.003, delta_per_notional=0.001),
        _scored("QQQ-A", edge=0.03, target=500, alpha_density=0.004, delta_per_notional=0.001),
        _scored("IWM-A", edge=0.01, target=500, alpha_density=0.001, delta_per_notional=0.01),
    ]
    result = optimize_basket(
        scored_candidates=rows,
        bankroll=10000,
        constraints=AllocationConstraints(max_positions=2, max_net_delta=1.0),
    )

    assert len(result.trades) == 2
    assert result.projected_net_delta <= 1.0


def test_score_incremental_capital_efficiency_positive_for_positive_edge():
    row = _scored("SPY-A", edge=0.02, target=500, alpha_density=0.002)
    score = score_incremental_capital_efficiency(row)
    assert score.expected_net_pnl > 0
    assert score.alpha_density > 0


def test_apply_greeks_overlay_returns_actions_when_outside_bands():
    actions = apply_greeks_overlay(net_delta=0.5, net_vega=-0.4, delta_band=0.1, vega_band=0.1)
    reasons = {row["reason"] for row in actions}
    assert "delta_overlay" in reasons
    assert "vega_overlay" in reasons
