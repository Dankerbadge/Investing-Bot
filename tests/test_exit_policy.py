from investing_bot.exit_policy import choose_exit_action


def test_exit_policy_prioritizes_assignment_risk_near_expiry():
    decision = choose_exit_action(
        broker_confirmed=True,
        unrealized_pnl=10.0,
        minutes_to_expiry=300,
        assignment_risk=0.9,
        spread_cost=0.02,
        hedge_drift=0.2,
        quote_quality_tier="realtime",
    )
    assert decision.action == "de_risk_close"
    assert decision.urgency > 0.9


def test_exit_policy_holds_when_broker_not_confirmed():
    decision = choose_exit_action(
        broker_confirmed=False,
        unrealized_pnl=10.0,
        minutes_to_expiry=300,
        assignment_risk=0.9,
        spread_cost=0.02,
        hedge_drift=0.2,
        quote_quality_tier="realtime",
    )
    assert decision.action == "hold"
    assert decision.reason == "pending_broker_truth"
