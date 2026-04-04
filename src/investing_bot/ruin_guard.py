from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuinGuardDecision:
    paused: bool
    kelly_multiplier: float
    reasons: tuple[str, ...]


def compute_ruin_guard(
    *,
    drawdown_fraction: float,
    daily_pnl_fraction: float,
    realized_volatility: float = 0.0,
    rolling_loss_streak: int = 0,
    stage: str = "scaled_1",
    max_drawdown_fraction: float = 0.20,
) -> RuinGuardDecision:
    reasons: list[str] = []
    paused = False

    stage_norm = str(stage or "").strip().lower() or "scaled_1"
    daily_stop = -0.025
    if stage_norm in {"probe", "scaled", "scaled_1"}:
        daily_stop = -0.015

    drawdown = max(0.0, float(drawdown_fraction))
    daily_pnl = float(daily_pnl_fraction)
    volatility = max(0.0, float(realized_volatility))
    loss_streak = max(0, int(rolling_loss_streak))

    if drawdown >= max_drawdown_fraction:
        paused = True
        reasons.append("max_drawdown_exceeded")
    if daily_pnl <= daily_stop:
        paused = True
        reasons.append("daily_drawdown_stop")

    multiplier = 1.0
    if max_drawdown_fraction > 0:
        multiplier *= max(0.0, 1.0 - min(0.9, (drawdown / max_drawdown_fraction) * 0.8))

    if volatility >= 0.05:
        multiplier *= 0.40
        reasons.append("realized_vol_hard")
    elif volatility >= 0.03:
        multiplier *= 0.70
        reasons.append("realized_vol_soft")

    if loss_streak >= 5:
        multiplier *= 0.50
        reasons.append("loss_streak_hard")
    elif loss_streak >= 3:
        multiplier *= 0.70
        reasons.append("loss_streak_soft")

    if paused:
        multiplier = 0.0

    return RuinGuardDecision(
        paused=paused,
        kelly_multiplier=round(max(0.0, min(1.0, multiplier)), 6),
        reasons=tuple(reasons),
    )
