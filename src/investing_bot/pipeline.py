from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .gating import LiquidityGate, evaluate_liquidity
from .models import Candidate, ScoredCandidate, SelectedTrade
from .risk import ConcentrationLimits, select_concentrated_portfolio
from .scoring import compute_net_executable_edge
from .sizing import fractional_kelly_fraction, full_kelly_fraction, notional_from_fraction


def build_trade_plan(
    *,
    candidates: list[Candidate],
    bankroll: float,
    gate: LiquidityGate,
    limits: ConcentrationLimits,
    kelly_fraction: float = 0.25,
    min_kelly_used: float = 0.002,
    max_kelly_used: float = 0.10,
) -> dict[str, Any]:
    scored: list[ScoredCandidate] = []

    for candidate in candidates:
        net_edge = compute_net_executable_edge(candidate)
        passes_gate, reasons = evaluate_liquidity(candidate, gate)

        kelly_full = full_kelly_fraction(
            win_probability=candidate.convergence_probability,
            payoff_multiple=candidate.payoff_multiple,
            loss_multiple=candidate.loss_multiple,
        )
        kelly_used = fractional_kelly_fraction(
            kelly_full=kelly_full,
            kelly_fraction=kelly_fraction,
            min_fraction=0.0,
            max_fraction=max_kelly_used,
        )
        target_notional = notional_from_fraction(bankroll=bankroll, fraction=kelly_used)

        gate_reasons = list(reasons)
        if net_edge <= 0:
            gate_reasons.append("net_edge_non_positive")
        if kelly_used < min_kelly_used:
            gate_reasons.append("kelly_used_below_min")

        executable = len(gate_reasons) == 0

        scored.append(
            ScoredCandidate(
                candidate=candidate,
                net_edge=round(net_edge, 6),
                executable=executable,
                gate_reasons=tuple(gate_reasons),
                kelly_full=round(kelly_full, 6),
                kelly_used=round(kelly_used, 6),
                target_notional=target_notional,
            )
        )

    selected: list[SelectedTrade] = select_concentrated_portfolio(
        scored_candidates=scored,
        bankroll=bankroll,
        limits=limits,
    )

    return {
        "candidate_count": len(candidates),
        "executable_count": sum(1 for row in scored if row.executable),
        "selected_count": len(selected),
        "selected": [asdict(row) for row in selected],
        "scored": [
            {
                "ticker": row.candidate.ticker,
                "underlying": row.candidate.underlying,
                "event_key": row.candidate.event_key,
                "strategy_family": row.candidate.strategy_family,
                "side": row.candidate.side,
                "net_edge": row.net_edge,
                "kelly_full": row.kelly_full,
                "kelly_used": row.kelly_used,
                "target_notional": row.target_notional,
                "executable": row.executable,
                "gate_reasons": list(row.gate_reasons),
            }
            for row in sorted(scored, key=lambda item: item.net_edge, reverse=True)
        ],
    }
