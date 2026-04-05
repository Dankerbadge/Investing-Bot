from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import ceil
from typing import Any

from .reconciliation import BrokerTruthSnapshot


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


def _timestamp_to_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if v > 1_000_000_000_000:
            return v / 1000.0
        return v
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    q_norm = min(1.0, max(0.0, float(q)))
    index = max(1, ceil(len(ordered) * q_norm))
    return float(ordered[index - 1])


@dataclass(frozen=True)
class PreflightResult:
    can_trade: bool
    hard_blocks: tuple[str, ...]
    warnings: tuple[str, ...]
    quote_age_p95_ms: float
    stream_gap_p99_seconds: float
    order_budget_utilization: float


def _quote_age_ms(row: dict[str, Any], now_epoch: float) -> float:
    quote_age_ms = _as_float(row.get("quote_age_ms"), default=-1.0)
    if quote_age_ms >= 0:
        return quote_age_ms

    quote_age_seconds = _as_float(row.get("quote_age_seconds"), default=-1.0)
    if quote_age_seconds >= 0:
        return quote_age_seconds * 1000.0

    quote_ts = _timestamp_to_epoch(
        row.get("quote_time")
        or row.get("quote_timestamp")
        or row.get("QUOTE_TIME_MILLIS")
    )
    if quote_ts is not None:
        return max(0.0, (now_epoch - quote_ts) * 1000.0)

    return 0.0


def run_preflight_checks(
    *,
    quote_rows: list[dict[str, Any]],
    broker_truth_snapshot: BrokerTruthSnapshot | None = None,
    now_utc: datetime | None = None,
    soft_order_budget_utilization: float = 0.70,
    hard_order_budget_utilization: float = 0.85,
    soft_quote_age_ms: float = 750.0,
    hard_quote_age_ms: float = 1500.0,
    hard_stream_gap_seconds: float = 5.0,
) -> PreflightResult:
    now_dt = now_utc or datetime.now(timezone.utc)
    now_epoch = now_dt.timestamp()

    hard_blocks: list[str] = []
    warnings: list[str] = []

    quote_ages = [_quote_age_ms(row, now_epoch) for row in quote_rows if isinstance(row, dict)]
    quote_age_p95 = _quantile(quote_ages, 0.95)

    stream_gaps = [max(0.0, _as_float(row.get("stream_gap_seconds"), 0.0)) for row in quote_rows if isinstance(row, dict)]
    stream_gap_p99 = _quantile(stream_gaps, 0.99)

    utilization = 0.0
    if broker_truth_snapshot is not None:
        utilization = float(broker_truth_snapshot.request_budget_utilization)
        if broker_truth_snapshot.delayed_quotes_detected:
            hard_blocks.append("broker_delayed_quotes_detected")
        if broker_truth_snapshot.request_budget_breached:
            hard_blocks.append("request_budget_breached")
        if broker_truth_snapshot.duplicate_client_order_ids:
            hard_blocks.append("duplicate_client_order_ids")
        if broker_truth_snapshot.duplicate_order_signatures:
            hard_blocks.append("duplicate_order_signatures")

    if quote_age_p95 > hard_quote_age_ms:
        hard_blocks.append("quote_age_p95_exceeded")
    elif quote_age_p95 > soft_quote_age_ms:
        warnings.append("quote_age_p95_soft_exceeded")

    if stream_gap_p99 > hard_stream_gap_seconds:
        hard_blocks.append("stream_gap_p99_exceeded")

    if utilization > hard_order_budget_utilization:
        hard_blocks.append("order_budget_hard_exceeded")
    elif utilization > soft_order_budget_utilization:
        warnings.append("order_budget_soft_exceeded")

    return PreflightResult(
        can_trade=(len(hard_blocks) == 0),
        hard_blocks=tuple(sorted(set(hard_blocks))),
        warnings=tuple(sorted(set(warnings))),
        quote_age_p95_ms=round(quote_age_p95, 6),
        stream_gap_p99_seconds=round(stream_gap_p99, 6),
        order_budget_utilization=round(utilization, 6),
    )
