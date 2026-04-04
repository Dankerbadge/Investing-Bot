from investing_bot.promotion import BucketPromotionMetrics, evaluate_stage_transition, stage_capital_multiplier


def test_promotion_flow_shadow_to_probe_to_scaled():
    metrics_probe = BucketPromotionMetrics(
        live_samples=25,
        lower_confidence_alpha_density=0.001,
        fill_brier_score=0.18,
        slippage_p75=0.015,
        broker_disagreement_rate=0.005,
        request_budget_breach_rate=0.0,
        delayed_quote_rate=0.0,
    )
    stage, _ = evaluate_stage_transition(
        current_stage="shadow",
        metrics=metrics_probe,
        capability_verified=True,
    )
    assert stage == "probe"

    metrics_scaled = BucketPromotionMetrics(
        live_samples=120,
        lower_confidence_alpha_density=0.002,
        fill_brier_score=0.12,
        slippage_p75=0.01,
        broker_disagreement_rate=0.003,
        request_budget_breach_rate=0.0,
        delayed_quote_rate=0.0,
    )
    stage, _ = evaluate_stage_transition(
        current_stage="probe",
        metrics=metrics_scaled,
        capability_verified=True,
    )
    assert stage == "scaled"


def test_scaled_stage_demotes_on_hard_drift():
    metrics_bad = BucketPromotionMetrics(
        live_samples=200,
        lower_confidence_alpha_density=-0.001,
        fill_brier_score=0.25,
        slippage_p75=0.03,
        broker_disagreement_rate=0.04,
        request_budget_breach_rate=0.04,
        delayed_quote_rate=0.06,
    )
    stage, reason = evaluate_stage_transition(
        current_stage="scaled",
        metrics=metrics_bad,
        capability_verified=True,
    )
    assert stage == "shadow"
    assert reason == "hard_drift_failure"
    assert stage_capital_multiplier("shadow") == 0.0
