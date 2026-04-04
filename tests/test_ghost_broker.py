from investing_bot.ghost_broker import simulate_passive_limit_fill


def test_ghost_broker_returns_penalties_and_partial_fill():
    result = simulate_passive_limit_fill(
        order_quantity=20,
        best_bid=1.0,
        best_ask=1.06,
        visible_depth_contracts=8,
        queue_ahead_contracts=20,
        urgency=0.8,
        wait_time_seconds=35,
        market_phase="open",
        random_seed=7,
    )

    assert 0.0 <= result.simulated_fill_probability <= 1.0
    assert 0 <= result.simulated_fill_quantity <= 20
    assert result.estimated_total_execution_penalty >= result.expected_slippage_dollars
