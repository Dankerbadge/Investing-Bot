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
    delayed_quotes_detected: bool = False,
    request_budget_breached: bool = False,
    duplicate_order_detected: bool = False,
) -> DeploymentDecision:
    reasons: list[str] = []
    paused = bool(pause_new_entries)

    if pause_new_entries:
        reasons.append("operator_paused")
    if delayed_quotes_detected:
        paused = True
        reasons.append("broker_delayed_quotes_detected")
    if request_budget_breached:
        paused = True
        reasons.append("broker_request_budget_breached")
    if duplicate_order_detected:
        paused = True
        reasons.append("duplicate_order_detected")

    stage_multiplier = stage_capital_multiplier(stage)
    drift_multiplier = min(1.0, max(0.0, float(drift_kelly_multiplier)))
    deploy_multiplier = min(1.0, max(0.0, float(deployment_capital_multiplier)))
    combined = stage_multiplier * drift_multiplier * deploy_multiplier

    if paused:
        combined = 0.0

    return DeploymentDecision(
        paused=paused,
        capital_multiplier=round(max(0.0, min(1.0, combined)), 6),
        reasons=tuple(reasons),
    )
