from investing_bot.bucket_health import BucketHealthThresholds, evaluate_bucket_health
from investing_bot.daily_rollup import BucketFact
from investing_bot.telemetry import TelemetrySummary


def test_bucket_health_healthy_when_metrics_are_strong():
    bucket = BucketFact(
        date="2026-04-04",
        bucket_key="spy-0dte",
        trade_count=80,
        filled_count=40,
        fill_rate=0.50,
        alpha_density_mean=0.002,
        fill_calibration_p95_abs_error=0.05,
        slippage_over_model_p75=0.10,
    )
    telemetry = TelemetrySummary(
        sample_count=80,
        stream_gap_p95_seconds=1.0,
        stream_gap_p99_seconds=2.0,
        quote_age_p95_ms=600,
        order_budget_peak_utilization=0.50,
        broker_mismatch_count=0,
        duplicate_order_incident_count=0,
        delayed_quote_event_count=0,
        fill_calibration_p95_abs_error=0.06,
        slippage_over_model_p75=0.10,
        alpha_density_lcb_p25=0.001,
    )

    health = evaluate_bucket_health(bucket_fact=bucket, telemetry_summary=telemetry)
    assert health.status == "healthy"
    assert health.capital_multiplier == 1.0


def test_bucket_health_halted_when_multiple_failures_accumulate():
    bucket = BucketFact(
        date="2026-04-04",
        bucket_key="qqq-weekly",
        trade_count=10,
        filled_count=1,
        fill_rate=0.10,
        alpha_density_mean=-0.001,
        fill_calibration_p95_abs_error=0.30,
        slippage_over_model_p75=0.50,
    )
    telemetry = TelemetrySummary(
        sample_count=20,
        stream_gap_p95_seconds=3.0,
        stream_gap_p99_seconds=8.0,
        quote_age_p95_ms=2400,
        order_budget_peak_utilization=0.92,
        broker_mismatch_count=2,
        duplicate_order_incident_count=1,
        delayed_quote_event_count=1,
        fill_calibration_p95_abs_error=0.25,
        slippage_over_model_p75=0.50,
        alpha_density_lcb_p25=-0.002,
    )

    thresholds = BucketHealthThresholds(min_trade_count=30)
    health = evaluate_bucket_health(bucket_fact=bucket, telemetry_summary=telemetry, thresholds=thresholds)
    assert health.status == "halted"
    assert health.capital_multiplier == 0.0
    assert "delayed_quotes_detected" in health.reasons
