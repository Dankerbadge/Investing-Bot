from __future__ import annotations

from dataclasses import dataclass

from .daily_rollup import BucketFact
from .telemetry import TelemetrySummary


@dataclass(frozen=True)
class BucketHealthThresholds:
    min_trade_count: int = 30
    min_fill_rate: float = 0.35
    min_alpha_density_mean: float = 0.0
    max_fill_calibration_p95_abs_error: float = 0.15
    max_slippage_over_model_p75: float = 0.25
    max_stream_gap_p99_seconds: float = 5.0
    max_order_budget_peak_utilization: float = 0.85
    max_duplicate_order_incidents: int = 0
    max_broker_mismatches: int = 0


@dataclass(frozen=True)
class BucketHealth:
    bucket_key: str
    date: str
    status: str
    score: float
    capital_multiplier: float
    reasons: tuple[str, ...]


def evaluate_bucket_health(
    *,
    bucket_fact: BucketFact,
    telemetry_summary: TelemetrySummary | None = None,
    thresholds: BucketHealthThresholds | None = None,
) -> BucketHealth:
    cfg = thresholds or BucketHealthThresholds()
    reasons: list[str] = []
    score = 1.0

    if bucket_fact.trade_count < cfg.min_trade_count:
        reasons.append("insufficient_trade_count")
        score -= 0.25
    if bucket_fact.fill_rate < cfg.min_fill_rate:
        reasons.append("fill_rate_too_low")
        score -= 0.20
    if bucket_fact.alpha_density_mean <= cfg.min_alpha_density_mean:
        reasons.append("alpha_density_non_positive")
        score -= 0.25
    if bucket_fact.fill_calibration_p95_abs_error > cfg.max_fill_calibration_p95_abs_error:
        reasons.append("fill_calibration_drift")
        score -= 0.15
    if bucket_fact.slippage_over_model_p75 > cfg.max_slippage_over_model_p75:
        reasons.append("slippage_drift")
        score -= 0.20

    if telemetry_summary is not None:
        if telemetry_summary.stream_gap_p99_seconds > cfg.max_stream_gap_p99_seconds:
            reasons.append("stream_gap_p99_exceeded")
            score -= 0.25
        if telemetry_summary.order_budget_peak_utilization > cfg.max_order_budget_peak_utilization:
            reasons.append("order_budget_peak_exceeded")
            score -= 0.20
        if telemetry_summary.duplicate_order_incident_count > cfg.max_duplicate_order_incidents:
            reasons.append("duplicate_order_incidents")
            score -= 0.30
        if telemetry_summary.broker_mismatch_count > cfg.max_broker_mismatches:
            reasons.append("broker_mismatch_incidents")
            score -= 0.30
        if telemetry_summary.delayed_quote_event_count > 0:
            reasons.append("delayed_quotes_detected")
            score -= 0.40

    score = max(0.0, min(1.0, round(score, 6)))

    if score <= 0.25:
        status = "halted"
        capital_multiplier = 0.0
    elif score <= 0.60:
        status = "degraded"
        capital_multiplier = 0.5
    else:
        status = "healthy"
        capital_multiplier = 1.0

    return BucketHealth(
        bucket_key=bucket_fact.bucket_key,
        date=bucket_fact.date,
        status=status,
        score=score,
        capital_multiplier=capital_multiplier,
        reasons=tuple(sorted(set(reasons))),
    )


def summarize_bucket_health(
    *,
    bucket_facts: list[BucketFact] | tuple[BucketFact, ...],
    telemetry_by_date: dict[str, TelemetrySummary] | None = None,
    thresholds: BucketHealthThresholds | None = None,
) -> tuple[BucketHealth, ...]:
    telemetry = telemetry_by_date or {}
    rows: list[BucketHealth] = []
    for bucket in bucket_facts:
        rows.append(
            evaluate_bucket_health(
                bucket_fact=bucket,
                telemetry_summary=telemetry.get(bucket.date),
                thresholds=thresholds,
            )
        )
    return tuple(rows)
