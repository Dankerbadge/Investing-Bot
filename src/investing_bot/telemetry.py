from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any


@dataclass(frozen=True)
class TelemetryPoint:
    timestamp: str = ""
    stream_gap_seconds: float = 0.0
    quote_age_ms: float = 0.0
    order_budget_utilization: float = 0.0
    broker_mismatch: bool = False
    duplicate_order_incident: bool = False
    delayed_quotes_detected: bool = False
    fill_calibration_abs_error: float = 0.0
    slippage_p75: float = 0.0
    modeled_slippage_p75: float = 0.0
    prevailing_spread: float = 0.0
    alpha_density_lcb: float = 0.0


@dataclass(frozen=True)
class TelemetrySummary:
    sample_count: int
    stream_gap_p95_seconds: float
    stream_gap_p99_seconds: float
    quote_age_p95_ms: float
    order_budget_peak_utilization: float
    broker_mismatch_count: int
    duplicate_order_incident_count: int
    delayed_quote_event_count: int
    fill_calibration_p95_abs_error: float
    slippage_over_model_p75: float
    alpha_density_lcb_p25: float


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    q_clamped = min(1.0, max(0.0, float(q)))
    ordered = sorted(values)
    rank = max(1, ceil(len(ordered) * q_clamped))
    return float(ordered[rank - 1])


def _coerce_point(point: TelemetryPoint | dict[str, Any]) -> TelemetryPoint:
    if isinstance(point, TelemetryPoint):
        return point
    if not isinstance(point, dict):
        return TelemetryPoint()
    spread = max(0.0, _as_float(point.get("prevailing_spread"), default=0.0))
    if spread <= 0.0:
        spread = max(0.0, _as_float(point.get("spread_cost"), default=0.0))
    return TelemetryPoint(
        timestamp=str(point.get("timestamp") or point.get("recorded_at") or ""),
        stream_gap_seconds=max(0.0, _as_float(point.get("stream_gap_seconds"), default=0.0)),
        quote_age_ms=max(0.0, _as_float(point.get("quote_age_ms"), default=0.0)),
        order_budget_utilization=min(2.0, max(0.0, _as_float(point.get("order_budget_utilization"), default=0.0))),
        broker_mismatch=_as_bool(point.get("broker_mismatch"), default=False),
        duplicate_order_incident=_as_bool(point.get("duplicate_order_incident"), default=False),
        delayed_quotes_detected=_as_bool(point.get("delayed_quotes_detected"), default=False),
        fill_calibration_abs_error=max(0.0, _as_float(point.get("fill_calibration_abs_error"), default=0.0)),
        slippage_p75=max(0.0, _as_float(point.get("slippage_p75"), default=0.0)),
        modeled_slippage_p75=max(0.0, _as_float(point.get("modeled_slippage_p75"), default=0.0)),
        prevailing_spread=spread,
        alpha_density_lcb=_as_float(point.get("alpha_density_lcb"), default=0.0),
    )


def aggregate_telemetry(points: list[TelemetryPoint | dict[str, Any]]) -> TelemetrySummary:
    rows = [_coerce_point(point) for point in points]
    if not rows:
        return TelemetrySummary(
            sample_count=0,
            stream_gap_p95_seconds=0.0,
            stream_gap_p99_seconds=0.0,
            quote_age_p95_ms=0.0,
            order_budget_peak_utilization=0.0,
            broker_mismatch_count=0,
            duplicate_order_incident_count=0,
            delayed_quote_event_count=0,
            fill_calibration_p95_abs_error=0.0,
            slippage_over_model_p75=0.0,
            alpha_density_lcb_p25=0.0,
        )

    gap = [row.stream_gap_seconds for row in rows]
    quote_age = [row.quote_age_ms for row in rows]
    budget = [row.order_budget_utilization for row in rows]
    fill_error = [row.fill_calibration_abs_error for row in rows]
    alpha_lcb = [row.alpha_density_lcb for row in rows]

    slippage_over_model: list[float] = []
    for row in rows:
        diff = max(0.0, row.slippage_p75 - row.modeled_slippage_p75)
        denom = row.prevailing_spread if row.prevailing_spread > 0 else 1.0
        slippage_over_model.append(diff / denom)

    return TelemetrySummary(
        sample_count=len(rows),
        stream_gap_p95_seconds=round(_quantile(gap, 0.95), 6),
        stream_gap_p99_seconds=round(_quantile(gap, 0.99), 6),
        quote_age_p95_ms=round(_quantile(quote_age, 0.95), 6),
        order_budget_peak_utilization=round(max(budget), 6),
        broker_mismatch_count=sum(1 for row in rows if row.broker_mismatch),
        duplicate_order_incident_count=sum(1 for row in rows if row.duplicate_order_incident),
        delayed_quote_event_count=sum(1 for row in rows if row.delayed_quotes_detected),
        fill_calibration_p95_abs_error=round(_quantile(fill_error, 0.95), 6),
        slippage_over_model_p75=round(_quantile(slippage_over_model, 0.75), 6),
        alpha_density_lcb_p25=round(_quantile(alpha_lcb, 0.25), 10),
    )
