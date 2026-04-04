from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExitDecision:
    action: str
    urgency: float
    expected_cost_penalty: float
    reason: str


def choose_exit_action(
    *,
    broker_confirmed: bool,
    unrealized_pnl: float,
    minutes_to_expiry: float,
    assignment_risk: float,
    spread_cost: float,
    hedge_drift: float,
    quote_quality_tier: str = "realtime",
) -> ExitDecision:
    """
    Conservative exit policy scaffold:
    - broker truth first
    - assignment/gap risk before PnL optimization
    - quote quality aware execution posture
    """

    quality = str(quote_quality_tier or "").strip().lower() or "unknown"
    dte_minutes = max(0.0, float(minutes_to_expiry))
    assign_risk = min(1.0, max(0.0, float(assignment_risk)))
    drift = min(1.0, max(0.0, float(hedge_drift)))
    spread = max(0.0, float(spread_cost))
    pnl = float(unrealized_pnl)

    if not broker_confirmed:
        return ExitDecision(action="hold", urgency=0.0, expected_cost_penalty=0.0, reason="pending_broker_truth")

    if quality in {"delayed", "stale"}:
        return ExitDecision(action="hold", urgency=0.0, expected_cost_penalty=0.0, reason="quote_quality_insufficient")

    if assign_risk >= 0.70 and dte_minutes <= 24 * 60:
        return ExitDecision(
            action="de_risk_close",
            urgency=0.95,
            expected_cost_penalty=round(spread * 0.85, 6),
            reason="elevated_assignment_risk_near_expiry",
        )

    if drift >= 0.60:
        return ExitDecision(
            action="hedge_rebalance",
            urgency=0.80,
            expected_cost_penalty=round(spread * 0.35, 6),
            reason="delta_drift_outside_band",
        )

    if pnl > 0 and spread <= 0.015:
        return ExitDecision(
            action="rest_exit",
            urgency=0.45,
            expected_cost_penalty=round(spread * 0.30, 6),
            reason="lock_gains_with_low_spread",
        )

    if pnl < 0 and assign_risk >= 0.40:
        return ExitDecision(
            action="cross_exit",
            urgency=0.75,
            expected_cost_penalty=round(spread * 0.95, 6),
            reason="loss_control_under_assignment_risk",
        )

    return ExitDecision(
        action="hold",
        urgency=0.20,
        expected_cost_penalty=0.0,
        reason="no_exit_trigger",
    )
