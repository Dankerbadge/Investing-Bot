from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .execution_learning import LearnedExecutionPrior, adjustments_for_candidate
from .execution_style import choose_execution_style
from .gating import LiquidityGate, evaluate_liquidity
from .models import Candidate, ScoredCandidate
from .reconciliation import BrokerTruthSnapshot
from .risk import ConcentrationLimits, select_concentrated_portfolio
from .scoring import compute_edge_breakdown
from .sizing import (
    dynamic_fractional_kelly_fraction,
    fractional_kelly_fraction,
    full_kelly_fraction,
    notional_from_fraction,
)


def build_trade_plan(
    *,
    candidates: list[Candidate],
    bankroll: float,
    gate: LiquidityGate,
    limits: ConcentrationLimits,
    execution_priors: dict[str, LearnedExecutionPrior] | None = None,
    kelly_fraction: float = 0.25,
    min_kelly_used: float = 0.002,
    max_kelly_used: float = 0.10,
    use_dynamic_kelly: bool = True,
    drawdown_fraction: float = 0.0,
    recent_order_requests_per_minute: float = 0.0,
    order_request_budget_per_minute: float = 120.0,
    broker_truth_snapshot: BrokerTruthSnapshot | None = None,
    require_broker_truth_clean: bool = True,
) -> dict[str, Any]:
    scored: list[ScoredCandidate] = []
    broker_observed_rpm = 0.0
    if broker_truth_snapshot is not None:
        broker_observed_rpm = float(broker_truth_snapshot.observed_requests_per_minute)
    effective_recent_rpm = max(0.0, float(recent_order_requests_per_minute), broker_observed_rpm)

    for candidate in candidates:
        adjustments = adjustments_for_candidate(candidate, execution_priors)
        edge = compute_edge_breakdown(candidate, adjustments)
        passes_gate, reasons = evaluate_liquidity(candidate, gate)
        metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
        broker_reasons: list[str] = []
        style_decision = choose_execution_style(
            candidate=candidate,
            adjusted_edge=edge.adjusted_net_edge,
            recent_order_requests_per_minute=effective_recent_rpm,
            order_request_budget_per_minute=order_request_budget_per_minute,
        )
        execution_adjusted_edge = edge.adjusted_net_edge
        style_adjusted_edge = (
            edge.adjusted_net_edge
            - style_decision.request_budget_penalty
            - style_decision.cancel_replace_race_penalty
        )
        risk_penalty = max(
            0.0,
            float(metadata.get("pre_trade_risk_penalty") or metadata.get("risk_penalty") or 0.0),
        )

        if require_broker_truth_clean and broker_truth_snapshot is not None:
            if broker_truth_snapshot.delayed_quotes_detected:
                broker_reasons.append("broker_delayed_quotes_detected")
                risk_penalty += 0.01
            if broker_truth_snapshot.request_budget_breached:
                broker_reasons.append("broker_request_budget_breached")
                risk_penalty += 0.005
            client_order_id = str(metadata.get("client_order_id") or "").strip()
            if client_order_id and client_order_id in set(broker_truth_snapshot.duplicate_client_order_ids):
                broker_reasons.append("duplicate_client_order_id_detected")
                risk_penalty += 0.02
            order_signature = str(metadata.get("order_signature") or "").strip()
            if order_signature and order_signature in set(broker_truth_snapshot.duplicate_order_signatures):
                broker_reasons.append("duplicate_order_signature_detected")
                risk_penalty += 0.02

        risk_adjusted_edge = style_adjusted_edge - risk_penalty

        kelly_full = full_kelly_fraction(
            win_probability=candidate.convergence_probability,
            payoff_multiple=candidate.payoff_multiple,
            loss_multiple=candidate.loss_multiple,
        )
        if use_dynamic_kelly:
            spread_regime_penalty = min(1.0, max(0.0, candidate.spread_cost / 0.10))
            slippage_penalty = min(1.0, max(0.0, edge.slippage_p95_penalty / 0.10))
            kelly_used = dynamic_fractional_kelly_fraction(
                kelly_full=kelly_full,
                base_kelly_fraction=kelly_fraction,
                confidence=candidate.confidence,
                drawdown_fraction=drawdown_fraction,
                model_error_score=edge.model_error_score,
                spread_regime_penalty=spread_regime_penalty,
                slippage_penalty=slippage_penalty,
                min_fraction=0.0,
                max_fraction=max_kelly_used,
            )
        else:
            kelly_used = fractional_kelly_fraction(
                kelly_full=kelly_full,
                kelly_fraction=kelly_fraction,
                min_fraction=0.0,
                max_fraction=max_kelly_used,
            )
        if risk_adjusted_edge <= 0 or not passes_gate:
            kelly_used = 0.0
        target_notional = notional_from_fraction(bankroll=bankroll, fraction=kelly_used)
        expected_holding_minutes = float(candidate.metadata.get("expected_holding_minutes") or 60.0)
        expected_holding_minutes = max(1.0, expected_holding_minutes)
        capital_minutes = max(1.0, target_notional * expected_holding_minutes)
        alpha_density = (
            max(0.0, risk_adjusted_edge) * max(0.0, edge.expected_fill_probability) / capital_minutes
        )

        gate_reasons = list(reasons)
        gate_reasons.extend(broker_reasons)
        if risk_adjusted_edge <= 0:
            gate_reasons.append("net_edge_non_positive")
        if kelly_used < min_kelly_used:
            gate_reasons.append("kelly_used_below_min")
        if edge.raw_net_edge > 0 and execution_adjusted_edge <= 0:
            gate_reasons.append("execution_learning_haircut_eliminated_edge")
        if execution_adjusted_edge > 0 and style_adjusted_edge <= 0:
            gate_reasons.append("execution_style_haircut_eliminated_edge")
        if style_adjusted_edge > 0 and risk_adjusted_edge <= 0:
            gate_reasons.append("risk_haircut_eliminated_edge")
        if not passes_gate:
            gate_reasons.append("liquidity_gate_failed")

        executable = len(gate_reasons) == 0

        scored.append(
            ScoredCandidate(
                candidate=candidate,
                net_edge=round(risk_adjusted_edge, 6),
                executable=executable,
                gate_reasons=tuple(gate_reasons),
                kelly_full=round(kelly_full, 6),
                kelly_used=round(kelly_used, 6),
                target_notional=target_notional,
                raw_net_edge=round(edge.raw_net_edge, 6),
                expected_fill_probability=round(edge.expected_fill_probability, 6),
                slippage_p95_penalty=round(edge.slippage_p95_penalty, 6),
                post_fill_alpha_decay_penalty=round(edge.post_fill_alpha_decay_penalty, 6),
                uncertainty_penalty=round(edge.uncertainty_penalty, 6),
                execution_penalty=round(
                    edge.execution_penalty
                    + style_decision.request_budget_penalty
                    + style_decision.cancel_replace_race_penalty,
                    6,
                ),
                model_error_score=round(edge.model_error_score, 6),
                alpha_density=round(alpha_density, 10),
                execution_style=style_decision.style,
                expected_replace_count=max(0, int(style_decision.expected_replace_count)),
                request_budget_penalty=round(style_decision.request_budget_penalty, 6),
                cancel_replace_race_penalty=round(style_decision.cancel_replace_race_penalty, 6),
                risk_penalty=round(risk_penalty, 6),
                execution_adjusted_edge=round(execution_adjusted_edge, 6),
                style_adjusted_edge=round(style_adjusted_edge, 6),
                risk_adjusted_edge=round(risk_adjusted_edge, 6),
            )
        )

    selected = select_concentrated_portfolio(
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
                "raw_net_edge": row.raw_net_edge,
                "kelly_full": row.kelly_full,
                "kelly_used": row.kelly_used,
                "target_notional": row.target_notional,
                "expected_fill_probability": row.expected_fill_probability,
                "slippage_p95_penalty": row.slippage_p95_penalty,
                "post_fill_alpha_decay_penalty": row.post_fill_alpha_decay_penalty,
                "uncertainty_penalty": row.uncertainty_penalty,
                "execution_penalty": row.execution_penalty,
                "model_error_score": row.model_error_score,
                "alpha_density": row.alpha_density,
                "execution_style": row.execution_style,
                "expected_replace_count": row.expected_replace_count,
                "request_budget_penalty": row.request_budget_penalty,
                "cancel_replace_race_penalty": row.cancel_replace_race_penalty,
                "risk_penalty": row.risk_penalty,
                "execution_adjusted_edge": row.execution_adjusted_edge,
                "style_adjusted_edge": row.style_adjusted_edge,
                "risk_adjusted_edge": row.risk_adjusted_edge,
                "executable": row.executable,
                "gate_reasons": list(row.gate_reasons),
            }
            for row in sorted(scored, key=lambda item: (item.alpha_density, item.net_edge), reverse=True)
        ],
    }
