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


def test_exit_policy_forces_close_short_american_near_close():
    decision = choose_exit_action(
        broker_confirmed=True,
        unrealized_pnl=-5.0,
        minutes_to_expiry=20,
        assignment_risk=0.8,
        spread_cost=0.03,
        hedge_drift=0.1,
        quote_quality_tier="realtime",
        is_short_american_single_name=True,
        fully_protected=False,
        minutes_to_close_et=10,
        is_expiration_day=True,
    )
    assert decision.action == "force_close_or_roll"


def test_exit_policy_ex_dividend_short_call_de_risk():
    decision = choose_exit_action(
        broker_confirmed=True,
        unrealized_pnl=1.0,
        minutes_to_expiry=2000,
        assignment_risk=0.2,
        spread_cost=0.01,
        hedge_drift=0.1,
        quote_quality_tier="realtime",
        is_short_call=True,
        near_ex_dividend=True,
        extrinsic_value=0.02,
    )
    assert decision.action == "de_risk_close"
