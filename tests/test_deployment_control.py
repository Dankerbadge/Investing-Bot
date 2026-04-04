from investing_bot.deployment_control import compute_deployment_decision


def test_deployment_decision_pauses_on_broker_risk():
    decision = compute_deployment_decision(
        stage="scaled",
        drift_kelly_multiplier=0.8,
        deployment_capital_multiplier=1.0,
        delayed_quotes_detected=True,
        request_budget_breached=False,
        duplicate_order_detected=False,
    )
    assert decision.paused is True
    assert decision.capital_multiplier == 0.0
    assert "broker_delayed_quotes_detected" in decision.reasons


def test_deployment_decision_scales_probe_capital():
    decision = compute_deployment_decision(
        stage="probe",
        drift_kelly_multiplier=0.5,
        deployment_capital_multiplier=0.8,
        pause_new_entries=False,
        delayed_quotes_detected=False,
        request_budget_breached=False,
        duplicate_order_detected=False,
    )
    # probe stage multiplier 0.05 * 0.5 * 0.8
    assert round(decision.capital_multiplier, 6) == 0.02
    assert decision.paused is False


def test_deployment_decision_soft_and_hard_budget_limits():
    soft = compute_deployment_decision(
        stage="scaled_1",
        drift_kelly_multiplier=1.0,
        deployment_capital_multiplier=1.0,
        order_budget_utilization=0.72,
    )
    hard = compute_deployment_decision(
        stage="scaled_1",
        drift_kelly_multiplier=1.0,
        deployment_capital_multiplier=1.0,
        order_budget_utilization=0.9,
    )
    assert soft.paused is False
    assert "order_budget_soft_limit" in soft.reasons
    assert hard.paused is True
    assert "order_budget_hard_limit" in hard.reasons
