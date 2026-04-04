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
        execution_style="synthetic_ladder",
        random_seed=7,
    )

    assert 0.0 <= result.simulated_fill_probability <= 1.0
    assert 0 <= result.simulated_fill_quantity <= 20
    assert result.estimated_total_execution_penalty >= result.expected_slippage_dollars
    assert result.execution_style == "synthetic_ladder"
    assert result.request_budget_penalty > 0.0


def test_native_walk_limit_uses_steps_and_lower_race_penalty_than_synthetic():
    native = simulate_passive_limit_fill(
        order_quantity=20,
        best_bid=1.0,
        best_ask=1.06,
        visible_depth_contracts=8,
        queue_ahead_contracts=20,
        urgency=0.8,
        wait_time_seconds=35,
        market_phase="open",
        execution_style="native_walk_limit",
        max_walk_steps=5,
        random_seed=7,
    )
    synthetic = simulate_passive_limit_fill(
        order_quantity=20,
        best_bid=1.0,
        best_ask=1.06,
        visible_depth_contracts=8,
        queue_ahead_contracts=20,
        urgency=0.8,
        wait_time_seconds=35,
        market_phase="open",
        execution_style="synthetic_ladder",
        max_walk_steps=5,
        random_seed=7,
    )

    assert native.walk_steps_used == 5
    assert native.cancel_replace_race_penalty < synthetic.cancel_replace_race_penalty
