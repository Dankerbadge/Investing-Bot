from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import json
from math import ceil
from pathlib import Path
from typing import Any

from .telemetry import TelemetrySummary, aggregate_telemetry


@dataclass(frozen=True)
class TradeFact:
    date: str
    source: str
    trade_count: int
    filled_count: int
    fill_rate: float
    realized_alpha_total: float
    realized_alpha_mean: float
    avg_slippage: float
    total_notional: float
    total_realized_pnl: float


@dataclass(frozen=True)
class BucketFact:
    date: str
    bucket_key: str
    trade_count: int
    filled_count: int
    fill_rate: float
    alpha_density_mean: float
    fill_calibration_p95_abs_error: float
    slippage_over_model_p75: float


@dataclass(frozen=True)
class PolicyFact:
    date: str
    policy_version: str
    decision_count: int
    unique_action_count: int
    realized_reward_mean: float


@dataclass(frozen=True)
class PortfolioFact:
    date: str
    ending_nlv: float
    realized_pnl: float
    total_max_loss: float
    net_delta: float
    net_vega: float
    max_drawdown_fraction: float


@dataclass(frozen=True)
class DailyRollup:
    trade_facts: tuple[TradeFact, ...]
    bucket_facts: tuple[BucketFact, ...]
    policy_facts: tuple[PolicyFact, ...]
    portfolio_facts: tuple[PortfolioFact, ...]
    telemetry_facts: dict[str, TelemetrySummary]


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


def _date_of(row: dict[str, Any]) -> str:
    if not isinstance(row, dict):
        return "unknown"
    for key in ("recorded_at", "timestamp", "captured_at", "event_time"):
        text = str(row.get(key) or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.date().isoformat()
        except ValueError:
            pass
        if len(text) >= 10:
            return text[:10]
    return "unknown"


def _source_of(row: dict[str, Any]) -> str:
    value = str(row.get("data_source") or row.get("source") or "live").strip().lower()
    if value in {"live", "paper", "ghost"}:
        return value
    return "live"


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    q_norm = min(1.0, max(0.0, float(q)))
    ordered = sorted(values)
    index = max(1, ceil(len(ordered) * q_norm))
    return float(ordered[index - 1])


def materialize_trade_facts(rows: list[dict[str, Any]]) -> tuple[TradeFact, ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault((_date_of(row), _source_of(row)), []).append(row)

    facts: list[TradeFact] = []
    for (date, source), group in sorted(grouped.items()):
        trade_count = len(group)
        filled = sum(1 for row in group if bool(row.get("filled")) or _as_float(row.get("fill_quantity"), 0.0) > 0)
        alpha = [_as_float(row.get("realized_alpha_density"), 0.0) for row in group]
        slippage = [_as_float(row.get("slippage"), _as_float(row.get("slippage_p75"), 0.0)) for row in group]
        notional = [_as_float(row.get("target_notional"), 0.0) for row in group]
        pnl = [_as_float(row.get("realized_pnl"), 0.0) for row in group]

        alpha_total = sum(alpha)
        facts.append(
            TradeFact(
                date=date,
                source=source,
                trade_count=trade_count,
                filled_count=filled,
                fill_rate=round((filled / trade_count) if trade_count else 0.0, 6),
                realized_alpha_total=round(alpha_total, 10),
                realized_alpha_mean=round((alpha_total / trade_count) if trade_count else 0.0, 10),
                avg_slippage=round((sum(slippage) / trade_count) if trade_count else 0.0, 8),
                total_notional=round(sum(notional), 6),
                total_realized_pnl=round(sum(pnl), 6),
            )
        )
    return tuple(facts)


def materialize_bucket_facts(rows: list[dict[str, Any]]) -> tuple[BucketFact, ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        bucket = str(row.get("bucket_key") or row.get("bucket") or "default").strip() or "default"
        grouped.setdefault((_date_of(row), bucket), []).append(row)

    facts: list[BucketFact] = []
    for (date, bucket), group in sorted(grouped.items()):
        trade_count = len(group)
        filled = sum(1 for row in group if bool(row.get("filled")) or _as_float(row.get("fill_quantity"), 0.0) > 0)
        alpha_density = [_as_float(row.get("realized_alpha_density"), 0.0) for row in group]
        fill_error = [_as_float(row.get("fill_calibration_abs_error"), 0.0) for row in group]

        slippage_over_model: list[float] = []
        for row in group:
            slip = _as_float(row.get("slippage"), _as_float(row.get("slippage_p75"), 0.0))
            modeled = _as_float(row.get("modeled_slippage"), _as_float(row.get("modeled_slippage_p75"), 0.0))
            spread = _as_float(row.get("prevailing_spread"), _as_float(row.get("spread_cost"), 0.0))
            denom = spread if spread > 0 else 1.0
            slippage_over_model.append(max(0.0, slip - modeled) / denom)

        facts.append(
            BucketFact(
                date=date,
                bucket_key=bucket,
                trade_count=trade_count,
                filled_count=filled,
                fill_rate=round((filled / trade_count) if trade_count else 0.0, 6),
                alpha_density_mean=round((sum(alpha_density) / trade_count) if trade_count else 0.0, 10),
                fill_calibration_p95_abs_error=round(_quantile(fill_error, 0.95), 6),
                slippage_over_model_p75=round(_quantile(slippage_over_model, 0.75), 6),
            )
        )
    return tuple(facts)


def materialize_policy_facts(rows: list[dict[str, Any]]) -> tuple[PolicyFact, ...]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        policy_version = str(row.get("policy_version") or "unknown").strip() or "unknown"
        grouped.setdefault((_date_of(row), policy_version), []).append(row)

    facts: list[PolicyFact] = []
    for (date, policy), group in sorted(grouped.items()):
        rewards = [_as_float(row.get("realized_alpha_density"), 0.0) for row in group]
        actions = {str(row.get("action") or row.get("policy_action") or "").strip() for row in group}
        actions = {action for action in actions if action}
        facts.append(
            PolicyFact(
                date=date,
                policy_version=policy,
                decision_count=len(group),
                unique_action_count=len(actions),
                realized_reward_mean=round((sum(rewards) / len(group)) if group else 0.0, 10),
            )
        )
    return tuple(facts)


def materialize_portfolio_facts(rows: list[dict[str, Any]]) -> tuple[PortfolioFact, ...]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault(_date_of(row), []).append(row)

    facts: list[PortfolioFact] = []
    for date, group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda row: str(row.get("recorded_at") or row.get("timestamp") or ""))
        nlv_series = [_as_float(row.get("net_liquidation_value"), 0.0) for row in ordered]
        peak = 0.0
        drawdowns: list[float] = []
        for value in nlv_series:
            peak = max(peak, value)
            if peak > 0:
                drawdowns.append(max(0.0, (peak - value) / peak))

        tail = ordered[-1] if ordered else {}
        facts.append(
            PortfolioFact(
                date=date,
                ending_nlv=round(_as_float(tail.get("net_liquidation_value"), 0.0), 6),
                realized_pnl=round(_as_float(tail.get("realized_pnl"), 0.0), 6),
                total_max_loss=round(_as_float(tail.get("total_max_loss"), 0.0), 6),
                net_delta=round(_as_float(tail.get("net_delta"), 0.0), 6),
                net_vega=round(_as_float(tail.get("net_vega"), 0.0), 6),
                max_drawdown_fraction=round(max(drawdowns) if drawdowns else 0.0, 6),
            )
        )
    return tuple(facts)


def materialize_telemetry_facts(rows: list[dict[str, Any]]) -> dict[str, TelemetrySummary]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        grouped.setdefault(_date_of(row), []).append(row)

    return {date: aggregate_telemetry(group) for date, group in sorted(grouped.items())}


def build_daily_rollup(
    *,
    decision_rows: list[dict[str, Any]],
    telemetry_rows: list[dict[str, Any]] | None = None,
    portfolio_rows: list[dict[str, Any]] | None = None,
) -> DailyRollup:
    return DailyRollup(
        trade_facts=materialize_trade_facts(decision_rows),
        bucket_facts=materialize_bucket_facts(decision_rows),
        policy_facts=materialize_policy_facts(decision_rows),
        portfolio_facts=materialize_portfolio_facts(portfolio_rows or []),
        telemetry_facts=materialize_telemetry_facts(telemetry_rows or []),
    )


def persist_daily_rollup(
    *,
    root_dir: Path,
    rollup: DailyRollup,
    as_of_date: str | None = None,
) -> Path:
    root = Path(root_dir)
    root.mkdir(parents=True, exist_ok=True)
    date_text = str(as_of_date or "").strip() or datetime.now(timezone.utc).date().isoformat()
    path = root / f"daily_rollup_{date_text}.json"

    payload = {
        "trade_facts": [asdict(row) for row in rollup.trade_facts],
        "bucket_facts": [asdict(row) for row in rollup.bucket_facts],
        "policy_facts": [asdict(row) for row in rollup.policy_facts],
        "portfolio_facts": [asdict(row) for row in rollup.portfolio_facts],
        "telemetry_facts": {key: asdict(value) for key, value in rollup.telemetry_facts.items()},
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return path
