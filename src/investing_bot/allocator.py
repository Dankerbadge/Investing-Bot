from __future__ import annotations

from dataclasses import dataclass

from .capital_efficiency import CapitalEfficiency, compute_capital_efficiency
from .models import ScoredCandidate


@dataclass(frozen=True)
class AllocationConstraints:
    max_positions: int = 3
    max_single_notional_fraction: float = 0.10
    max_total_notional_fraction: float = 0.35
    max_total_max_loss_fraction: float = 0.20
    max_per_underlying_fraction: float = 0.15
    max_per_event_fraction: float = 0.20
    max_net_delta: float = 1.0
    max_net_vega: float = 1.0


@dataclass(frozen=True)
class AllocatedTrade:
    ticker: str
    underlying: str
    event_key: str
    strategy_family: str
    target_notional: float
    expected_net_pnl: float
    alpha_density: float
    incremental_max_loss: float
    delta_exposure: float
    vega_exposure: float
    execution_style: str


@dataclass(frozen=True)
class AllocationResult:
    trades: tuple[AllocatedTrade, ...]
    total_notional: float
    total_expected_net_pnl: float
    total_max_loss: float
    portfolio_alpha_density: float
    projected_net_delta: float
    projected_net_vega: float
    rejected_count: int


def score_incremental_capital_efficiency(candidate: ScoredCandidate) -> CapitalEfficiency:
    expected_holding_minutes = float(candidate.candidate.metadata.get("expected_holding_minutes") or 60.0)
    expected_holding_minutes = max(1.0, expected_holding_minutes)
    expected_net_pnl = max(0.0, candidate.net_edge) * max(0.0, candidate.expected_fill_probability) * max(0.0, candidate.target_notional)
    max_loss = max(0.0, candidate.target_notional) * max(1.0, float(candidate.candidate.loss_multiple))
    shock_loss = max_loss
    return compute_capital_efficiency(
        expected_net_pnl=expected_net_pnl,
        notional=max(0.0, candidate.target_notional),
        expected_holding_minutes=expected_holding_minutes,
        incremental_max_loss=max_loss,
        incremental_shock_loss=shock_loss,
    )


def optimize_basket(
    *,
    scored_candidates: list[ScoredCandidate],
    bankroll: float,
    constraints: AllocationConstraints,
    current_net_delta: float = 0.0,
    current_net_vega: float = 0.0,
) -> AllocationResult:
    if bankroll <= 0:
        return AllocationResult(
            trades=(),
            total_notional=0.0,
            total_expected_net_pnl=0.0,
            total_max_loss=0.0,
            portfolio_alpha_density=0.0,
            projected_net_delta=round(float(current_net_delta), 6),
            projected_net_vega=round(float(current_net_vega), 6),
            rejected_count=len(scored_candidates),
        )

    ranked = sorted(
        [row for row in scored_candidates if row.executable and row.net_edge > 0 and row.target_notional > 0],
        key=lambda row: (
            score_incremental_capital_efficiency(row).alpha_density,
            row.alpha_density,
            row.net_edge,
            row.candidate.confidence,
        ),
        reverse=True,
    )

    selected: list[AllocatedTrade] = []
    rejected = 0

    total_notional = 0.0
    total_expected = 0.0
    total_max_loss = 0.0
    total_capital_minutes = 0.0
    running_delta = float(current_net_delta)
    running_vega = float(current_net_vega)

    per_underlying_notional: dict[str, float] = {}
    per_event_notional: dict[str, float] = {}

    max_single = bankroll * constraints.max_single_notional_fraction
    max_total = bankroll * constraints.max_total_notional_fraction
    max_total_max_loss = bankroll * constraints.max_total_max_loss_fraction
    max_underlying = bankroll * constraints.max_per_underlying_fraction
    max_event = bankroll * constraints.max_per_event_fraction

    for row in ranked:
        if len(selected) >= constraints.max_positions:
            rejected += 1
            continue

        target = min(max_single, max(0.0, row.target_notional))
        if target <= 0:
            rejected += 1
            continue
        if total_notional + target > max_total:
            rejected += 1
            continue

        candidate = row.candidate
        underlying = candidate.underlying
        event_key = candidate.event_key
        if per_underlying_notional.get(underlying, 0.0) + target > max_underlying:
            rejected += 1
            continue
        if per_event_notional.get(event_key, 0.0) + target > max_event:
            rejected += 1
            continue

        max_loss = target * max(1.0, float(candidate.loss_multiple))
        if total_max_loss + max_loss > max_total_max_loss:
            rejected += 1
            continue

        delta_per_notional = float(candidate.metadata.get("delta_per_notional") or 0.0)
        vega_per_notional = float(candidate.metadata.get("vega_per_notional") or 0.0)
        projected_delta = running_delta + (delta_per_notional * target)
        projected_vega = running_vega + (vega_per_notional * target)
        if abs(projected_delta) > constraints.max_net_delta:
            rejected += 1
            continue
        if abs(projected_vega) > constraints.max_net_vega:
            rejected += 1
            continue

        efficiency = score_incremental_capital_efficiency(
            ScoredCandidate(
                candidate=candidate,
                net_edge=row.net_edge,
                executable=row.executable,
                gate_reasons=row.gate_reasons,
                kelly_full=row.kelly_full,
                kelly_used=row.kelly_used,
                target_notional=target,
                raw_net_edge=row.raw_net_edge,
                expected_fill_probability=row.expected_fill_probability,
                slippage_p95_penalty=row.slippage_p95_penalty,
                post_fill_alpha_decay_penalty=row.post_fill_alpha_decay_penalty,
                uncertainty_penalty=row.uncertainty_penalty,
                execution_penalty=row.execution_penalty,
                model_error_score=row.model_error_score,
                alpha_density=row.alpha_density,
                execution_style=row.execution_style,
            )
        )
        expected_pnl = efficiency.expected_net_pnl

        selected.append(
            AllocatedTrade(
                ticker=candidate.ticker,
                underlying=underlying,
                event_key=event_key,
                strategy_family=candidate.strategy_family,
                target_notional=round(target, 2),
                expected_net_pnl=round(expected_pnl, 6),
                alpha_density=round(efficiency.alpha_density, 12),
                incremental_max_loss=round(max_loss, 6),
                delta_exposure=round(delta_per_notional * target, 6),
                vega_exposure=round(vega_per_notional * target, 6),
                execution_style=row.execution_style,
            )
        )

        total_notional += target
        total_expected += expected_pnl
        total_max_loss += max_loss
        total_capital_minutes += efficiency.capital_minutes
        running_delta = projected_delta
        running_vega = projected_vega
        per_underlying_notional[underlying] = per_underlying_notional.get(underlying, 0.0) + target
        per_event_notional[event_key] = per_event_notional.get(event_key, 0.0) + target

    alpha_density = (total_expected / total_capital_minutes) if total_capital_minutes > 0 else 0.0
    return AllocationResult(
        trades=tuple(selected),
        total_notional=round(total_notional, 2),
        total_expected_net_pnl=round(total_expected, 6),
        total_max_loss=round(total_max_loss, 6),
        portfolio_alpha_density=round(alpha_density, 12),
        projected_net_delta=round(running_delta, 6),
        projected_net_vega=round(running_vega, 6),
        rejected_count=rejected,
    )


def apply_greeks_overlay(
    *,
    net_delta: float,
    net_vega: float,
    target_delta: float = 0.0,
    target_vega: float = 0.0,
    delta_band: float = 0.10,
    vega_band: float = 0.10,
    delta_hedge_symbol: str = "SPY",
    vega_hedge_symbol: str = "VIX",
) -> tuple[dict[str, float | str], ...]:
    actions: list[dict[str, float | str]] = []

    delta_gap = float(net_delta) - float(target_delta)
    if abs(delta_gap) > max(0.0, float(delta_band)):
        actions.append(
            {
                "symbol": str(delta_hedge_symbol).strip().upper() or "SPY",
                "side": "sell" if delta_gap > 0 else "buy",
                "size": round(abs(delta_gap), 6),
                "reason": "delta_overlay",
            }
        )

    vega_gap = float(net_vega) - float(target_vega)
    if abs(vega_gap) > max(0.0, float(vega_band)):
        actions.append(
            {
                "symbol": str(vega_hedge_symbol).strip().upper() or "VIX",
                "side": "sell" if vega_gap > 0 else "buy",
                "size": round(abs(vega_gap), 6),
                "reason": "vega_overlay",
            }
        )

    return tuple(actions)
