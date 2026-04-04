from __future__ import annotations

from dataclasses import dataclass

from .models import ScoredCandidate, SelectedTrade


@dataclass(frozen=True)
class ConcentrationLimits:
    max_open_positions: int = 3
    max_per_underlying: int = 1
    max_per_event: int = 1
    max_per_strategy_family: int = 2
    max_single_position_fraction: float = 0.10
    max_gross_notional_fraction: float = 0.35
    max_shock_loss_fraction: float = 0.20


def select_concentrated_portfolio(
    *,
    scored_candidates: list[ScoredCandidate],
    bankroll: float,
    limits: ConcentrationLimits,
) -> list[SelectedTrade]:
    if bankroll <= 0:
        return []

    sorted_candidates = sorted(
        scored_candidates,
        key=lambda item: (item.net_edge, item.kelly_used, item.candidate.confidence),
        reverse=True,
    )

    max_single_notional = bankroll * limits.max_single_position_fraction
    max_gross_notional = bankroll * limits.max_gross_notional_fraction

    selected: list[SelectedTrade] = []
    underlying_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    strategy_counts: dict[str, int] = {}
    gross_notional = 0.0
    worst_case_loss_notional = 0.0

    for item in sorted_candidates:
        if len(selected) >= limits.max_open_positions:
            break
        if not item.executable or item.net_edge <= 0:
            continue

        candidate = item.candidate
        if underlying_counts.get(candidate.underlying, 0) >= limits.max_per_underlying:
            continue
        if event_counts.get(candidate.event_key, 0) >= limits.max_per_event:
            continue
        if strategy_counts.get(candidate.strategy_family, 0) >= limits.max_per_strategy_family:
            continue

        target = min(item.target_notional, max_single_notional)
        if target <= 0:
            continue
        if gross_notional + target > max_gross_notional:
            continue
        incremental_worst_case = target * max(1.0, float(candidate.loss_multiple))
        if (worst_case_loss_notional + incremental_worst_case) > (bankroll * limits.max_shock_loss_fraction):
            continue

        selected.append(
            SelectedTrade(
                ticker=candidate.ticker,
                underlying=candidate.underlying,
                event_key=candidate.event_key,
                strategy_family=candidate.strategy_family,
                side=candidate.side,
                net_edge=round(item.net_edge, 6),
                kelly_used=round(item.kelly_used, 6),
                target_notional=round(target, 2),
                confidence=round(candidate.confidence, 6),
                raw_net_edge=round(item.raw_net_edge, 6),
            )
        )

        underlying_counts[candidate.underlying] = underlying_counts.get(candidate.underlying, 0) + 1
        event_counts[candidate.event_key] = event_counts.get(candidate.event_key, 0) + 1
        strategy_counts[candidate.strategy_family] = strategy_counts.get(candidate.strategy_family, 0) + 1
        gross_notional += target
        worst_case_loss_notional += incremental_worst_case

    return selected
