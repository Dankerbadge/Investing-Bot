from investing_bot.alerts import generate_alerts
from investing_bot.ops_dashboard import build_ops_dashboard
from investing_bot.telemetry import TelemetryPoint, aggregate_telemetry


def test_telemetry_aggregation_and_alert_generation():
    summary = aggregate_telemetry(
        [
            TelemetryPoint(
                stream_gap_seconds=1.0,
                quote_age_ms=300,
                order_budget_utilization=0.40,
                fill_calibration_abs_error=0.05,
                slippage_p75=0.01,
                modeled_slippage_p75=0.008,
                prevailing_spread=0.02,
                alpha_density_lcb=0.001,
            ),
            TelemetryPoint(
                stream_gap_seconds=6.2,
                quote_age_ms=2100,
                order_budget_utilization=0.91,
                duplicate_order_incident=True,
                fill_calibration_abs_error=0.20,
                slippage_p75=0.03,
                modeled_slippage_p75=0.01,
                prevailing_spread=0.04,
                alpha_density_lcb=-0.002,
            ),
        ]
    )

    assert summary.sample_count == 2
    assert summary.stream_gap_p99_seconds == 6.2
    assert summary.order_budget_peak_utilization == 0.91

    alerts = generate_alerts(summary)
    codes = {alert.code for alert in alerts}
    assert "stream_gap_p99_exceeded" in codes
    assert "order_budget_hard_limit" in codes
    assert "duplicate_order_incident" in codes


def test_ops_dashboard_health_uses_alert_severity():
    summary = aggregate_telemetry([TelemetryPoint(stream_gap_seconds=0.5)])
    alerts = generate_alerts(summary)
    dashboard = build_ops_dashboard(
        summary=summary,
        alerts=alerts,
        stage="scaled_1",
        capital_multiplier=0.10,
    )
    assert dashboard["health"] == "healthy"

    severe_summary = aggregate_telemetry([TelemetryPoint(stream_gap_seconds=7.0, order_budget_utilization=0.9)])
    severe_alerts = generate_alerts(severe_summary)
    severe_dashboard = build_ops_dashboard(
        summary=severe_summary,
        alerts=severe_alerts,
        stage="probe",
        capital_multiplier=0.0,
    )
    assert severe_dashboard["health"] == "halted"
    assert severe_dashboard["alert_levels"]["critical"] >= 1
