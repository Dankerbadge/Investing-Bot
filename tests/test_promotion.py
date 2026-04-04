from investing_bot.promotion import BucketPromotionMetrics, evaluate_stage_transition, stage_capital_multiplier


def test_promotion_flow_shadow_to_probe_to_scaled():
    metrics_probe = BucketPromotionMetrics(
        shadow_opportunities=200,
        shadow_would_trade_count=50,
        shadow_alpha_density_p25=0.0001,
        median_predicted_fill_probability=0.40,
        hard_kills_last_5_sessions=0,
    )
    stage, _ = evaluate_stage_transition(
        current_stage="shadow",
        metrics=metrics_probe,
        capability_verified=True,
    )
    assert stage == "probe"

    metrics_scaled = BucketPromotionMetrics(
        reconciled_round_trips=50,
        lower_confidence_alpha_density=0.002,
        fill_calibration_abs_error=0.05,
        slippage_p75=0.007,
        modeled_slippage_p75=0.005,
        prevailing_spread=0.03,
        unresolved_duplicate_order_incidents=0,
        request_budget_breaches_last_10_sessions=0,
        latency_hard_kills_last_10_sessions=0,
        event_context_coverage=0.8,
        regime_context_coverage=0.8,
    )
    stage, _ = evaluate_stage_transition(
        current_stage="probe",
        metrics=metrics_scaled,
        capability_verified=True,
    )
    assert stage == "scaled_1"


def test_scaled_stage_demotes_on_hard_drift():
    metrics_bad = BucketPromotionMetrics(
        reconciled_round_trips=100,
        lower_confidence_alpha_density=0.001,
        fill_calibration_abs_error=0.05,
        slippage_p75=0.01,
        modeled_slippage_p75=0.005,
        prevailing_spread=0.03,
        unresolved_duplicate_order_incidents=0,
        request_budget_breaches_last_10_sessions=0,
        latency_hard_kills_last_10_sessions=0,
        event_context_coverage=1.0,
        regime_context_coverage=1.0,
        broker_truth_mismatch_changes_pnl=True,
    )
    stage, reason = evaluate_stage_transition(
        current_stage="scaled_2",
        metrics=metrics_bad,
        capability_verified=True,
    )
    assert stage == "probe"
    assert reason == "broker_truth_mismatch_demotion"
    assert stage_capital_multiplier("shadow") == 0.0


def test_disabled_promotes_to_shadow_when_readiness_met():
    metrics = BucketPromotionMetrics(
        sessions_without_delayed_quotes=3,
        stream_gap_p99_seconds=2.0,
        peak_order_budget_utilization=0.4,
        unresolved_broker_mismatches=0,
    )
    stage, reason = evaluate_stage_transition(
        current_stage="disabled",
        metrics=metrics,
        capability_verified=True,
    )
    assert stage == "shadow"
    assert reason == "shadow_threshold_met"
