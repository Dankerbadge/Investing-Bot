from investing_bot.capital_efficiency import compute_capital_efficiency, rank_by_capital_efficiency


def test_capital_efficiency_metrics_are_computed():
    metrics = compute_capital_efficiency(
        expected_net_pnl=15.0,
        notional=1000.0,
        expected_holding_minutes=30,
        incremental_max_loss=200.0,
        incremental_shock_loss=250.0,
    )

    assert metrics.capital_minutes == 30000.0
    assert metrics.alpha_density == 0.0005
    assert metrics.pnl_per_max_loss == 0.075


def test_rank_by_capital_efficiency_orders_highest_alpha_density_first():
    low = compute_capital_efficiency(
        expected_net_pnl=5.0,
        notional=1000.0,
        expected_holding_minutes=60,
        incremental_max_loss=200.0,
        incremental_shock_loss=200.0,
    )
    high = compute_capital_efficiency(
        expected_net_pnl=8.0,
        notional=800.0,
        expected_holding_minutes=20,
        incremental_max_loss=160.0,
        incremental_shock_loss=200.0,
    )

    ranked = rank_by_capital_efficiency([("low", low), ("high", high)])
    assert ranked[0][0] == "high"
