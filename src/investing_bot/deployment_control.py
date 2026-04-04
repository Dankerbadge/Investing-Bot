from __future__ import annotations

from dataclasses import dataclass

from .promotion import stage_capital_multiplier


@dataclass(frozen=True)
class DeploymentDecision:
    paused: bool
    capital_multiplier: float
    reasons: tuple[str, ...]


def compute_deployment_decision(
    *,
    stage: str,
    drift_kelly_multiplier: float,
    deployment_capital_multiplier: float = 1.0,
    pause_new_entries: bool = False,
    order_budget_utilization: float = 0.0,
    soft_order_budget_utilization: float = 0.70,
    hard_order_budget_utilization: float = 0.85,
    stream_gap_seconds: float = 0.0,
    hard_stream_gap_seconds: float = 5.0,
    daily_pnl_fraction: float = 0.0,
    regime_multiplier: float = 1.0,
    event_risk_score: float = 0.0,
    delayed_quotes_detected: bool = False,
    request_budget_breached: bool = False,
    duplicate_order_detected: bool = False,
) -> DeploymentDecision:
    reasons: list[str] = []
    paused = bool(pause_new_entries)
    stage_norm = str(stage or "").strip().lower()

    if pause_new_entries:
        reasons.append("operator_paused")
    if float(order_budget_utilization) >= float(soft_order_budget_utilization):
        reasons.append("order_budget_soft_limit")
    if float(order_budget_utilization) >= float(hard_order_budget_utilization):
        paused = True
        reasons.append("order_budget_hard_limit")
    if float(stream_gap_seconds) > float(hard_stream_gap_seconds):
        paused = True
        reasons.append("stream_gap_hard_limit")
    if delayed_quotes_detected:
        paused = True
        reasons.append("broker_delayed_quotes_detected")
    if request_budget_breached:
        paused = True
        reasons.append("broker_request_budget_breached")
    if duplicate_order_detected:
        paused = True
        reasons.append("duplicate_order_detected")

    if float(event_risk_score) >= 0.80:
        paused = True
        reasons.append("event_risk_hard_limit")

    daily_stop = -0.025
    if stage_norm in {"probe", "scaled", "scaled_1"}:
        daily_stop = -0.015
    if float(daily_pnl_fraction) <= daily_stop:
        paused = True
        reasons.append("daily_drawdown_stop")

    stage_multiplier = stage_capital_multiplier(stage_norm)
    drift_multiplier = min(1.0, max(0.0, float(drift_kelly_multiplier)))
    deploy_multiplier = min(1.0, max(0.0, float(deployment_capital_multiplier)))
    regime_mult = min(1.0, max(0.0, float(regime_multiplier)))
    combined = stage_multiplier * drift_multiplier * deploy_multiplier * regime_mult

    if float(order_budget_utilization) >= float(soft_order_budget_utilization) and not paused:
        combined *= 0.5

    if paused:
        combined = 0.0

    return DeploymentDecision(
        paused=paused,
        capital_multiplier=round(max(0.0, min(1.0, combined)), 6),
        reasons=tuple(reasons),
    )
