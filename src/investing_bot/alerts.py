from __future__ import annotations

from dataclasses import dataclass

from .telemetry import TelemetrySummary


@dataclass(frozen=True)
class Alert:
    level: str
    code: str
    message: str
    value: float = 0.0
    threshold: float = 0.0


@dataclass(frozen=True)
class AlertThresholds:
    max_stream_gap_p99_seconds: float = 5.0
    max_quote_age_p95_ms: float = 1500.0
    soft_order_budget_utilization: float = 0.70
    hard_order_budget_utilization: float = 0.85
    max_fill_calibration_p95_abs_error: float = 0.15
    max_slippage_over_model_p75: float = 0.25


def generate_alerts(summary: TelemetrySummary, thresholds: AlertThresholds | None = None) -> tuple[Alert, ...]:
    cfg = thresholds or AlertThresholds()
    alerts: list[Alert] = []

    if summary.delayed_quote_event_count > 0:
        alerts.append(
            Alert(
                level="critical",
                code="delayed_quotes_detected",
                message="Delayed quotes were observed in the telemetry window.",
                value=float(summary.delayed_quote_event_count),
                threshold=0.0,
            )
        )

    if summary.broker_mismatch_count > 0:
        alerts.append(
            Alert(
                level="critical",
                code="broker_mismatch_detected",
                message="Broker-truth mismatches were detected and require reconciliation.",
                value=float(summary.broker_mismatch_count),
                threshold=0.0,
            )
        )

    if summary.duplicate_order_incident_count > 0:
        alerts.append(
            Alert(
                level="critical",
                code="duplicate_order_incident",
                message="Duplicate-order incidents were observed.",
                value=float(summary.duplicate_order_incident_count),
                threshold=0.0,
            )
        )

    if summary.stream_gap_p99_seconds > cfg.max_stream_gap_p99_seconds:
        alerts.append(
            Alert(
                level="critical",
                code="stream_gap_p99_exceeded",
                message="Stream gap p99 exceeds the hard limit.",
                value=summary.stream_gap_p99_seconds,
                threshold=cfg.max_stream_gap_p99_seconds,
            )
        )

    if summary.quote_age_p95_ms > cfg.max_quote_age_p95_ms:
        alerts.append(
            Alert(
                level="warn",
                code="quote_age_p95_exceeded",
                message="Quote-age p95 is above the operating threshold.",
                value=summary.quote_age_p95_ms,
                threshold=cfg.max_quote_age_p95_ms,
            )
        )

    if summary.order_budget_peak_utilization >= cfg.hard_order_budget_utilization:
        alerts.append(
            Alert(
                level="critical",
                code="order_budget_hard_limit",
                message="Order request budget exceeded the hard utilization limit.",
                value=summary.order_budget_peak_utilization,
                threshold=cfg.hard_order_budget_utilization,
            )
        )
    elif summary.order_budget_peak_utilization >= cfg.soft_order_budget_utilization:
        alerts.append(
            Alert(
                level="warn",
                code="order_budget_soft_limit",
                message="Order request budget exceeded the soft utilization limit.",
                value=summary.order_budget_peak_utilization,
                threshold=cfg.soft_order_budget_utilization,
            )
        )

    if summary.fill_calibration_p95_abs_error > cfg.max_fill_calibration_p95_abs_error:
        alerts.append(
            Alert(
                level="warn",
                code="fill_calibration_drift",
                message="Fill calibration error drifted above threshold.",
                value=summary.fill_calibration_p95_abs_error,
                threshold=cfg.max_fill_calibration_p95_abs_error,
            )
        )

    if summary.slippage_over_model_p75 > cfg.max_slippage_over_model_p75:
        alerts.append(
            Alert(
                level="warn",
                code="slippage_drift",
                message="Observed slippage exceeded modeled slippage by too much.",
                value=summary.slippage_over_model_p75,
                threshold=cfg.max_slippage_over_model_p75,
            )
        )

    return tuple(alerts)
