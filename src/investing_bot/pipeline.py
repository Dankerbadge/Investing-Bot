from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .deployment_control import compute_deployment_decision
from .execution_learning import LearnedExecutionPrior, adjustments_for_candidate
from .execution_style import choose_execution_style
from .gating import LiquidityGate, evaluate_liquidity
from .latency import build_latency_profile, estimate_latency_penalty, latency_kill_switch
from .models import Candidate, ScoredCandidate
from .policy import ActionPolicyStats, choose_entry_action
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
    live_execution_priors: dict[str, LearnedExecutionPrior] | None = None,
    kelly_fraction: float = 0.25,
    min_kelly_used: float = 0.002,
    max_kelly_used: float = 0.10,
    use_dynamic_kelly: bool = True,
    drawdown_fraction: float = 0.0,
    drift_kelly_multiplier: float = 1.0,
    deployment_capital_multiplier: float = 1.0,
    pause_new_entries: bool = False,
    enforce_live_prior_size_cap: bool = True,
    policy_state: dict[str, ActionPolicyStats] | None = None,
    policy_min_confirmed_samples: int = 20,
    recent_order_requests_per_minute: float = 0.0,
    order_request_budget_per_minute: float = 120.0,
    broker_truth_snapshot: BrokerTruthSnapshot | None = None,
    require_broker_truth_clean: bool = True,
    max_quote_age_ms: float = 3000.0,
    max_decision_ms: float = 1200.0,
    max_submit_to_ack_ms: float = 5000.0,
) -> dict[str, Any]:
    def _dedupe_reasons(items: list[str]) -> list[str]:
        deduped: list[str] = []
        for item in items:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    scored: list[ScoredCandidate] = []
    broker_observed_rpm = 0.0
    duplicate_client_ids: set[str] = set()
    duplicate_signatures: set[str] = set()
    if broker_truth_snapshot is not None:
        broker_observed_rpm = float(broker_truth_snapshot.observed_requests_per_minute)
        duplicate_client_ids = set(broker_truth_snapshot.duplicate_client_order_ids)
        duplicate_signatures = set(broker_truth_snapshot.duplicate_order_signatures)
    effective_recent_rpm = max(0.0, float(recent_order_requests_per_minute), broker_observed_rpm)
    drift_multiplier = min(1.0, max(0.0, float(drift_kelly_multiplier)))
    deployment_multiplier = min(1.0, max(0.0, float(deployment_capital_multiplier)))
    duplicate_order_detected = bool(duplicate_client_ids or duplicate_signatures)

    for candidate in candidates:
        adjustments = adjustments_for_candidate(candidate, execution_priors)
        edge = compute_edge_breakdown(candidate, adjustments)
        live_cap_penalty = 0.0
        expected_fill_probability = edge.expected_fill_probability
        execution_adjusted_edge = edge.adjusted_net_edge
        if enforce_live_prior_size_cap and live_execution_priors:
            live_adjustments = adjustments_for_candidate(candidate, live_execution_priors)
            live_edge = compute_edge_breakdown(candidate, live_adjustments)
            if execution_adjusted_edge > live_edge.adjusted_net_edge:
                live_cap_penalty = max(0.0, execution_adjusted_edge - live_edge.adjusted_net_edge)
                execution_adjusted_edge = live_edge.adjusted_net_edge
                expected_fill_probability = min(expected_fill_probability, live_edge.expected_fill_probability)

        passes_gate, reasons = evaluate_liquidity(candidate, gate)
        metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
        broker_reasons: list[str] = []
        policy_reasons: list[str] = []
        hard_block = False
        deployment_stage = str(metadata.get("deployment_stage") or "scaled").strip().lower()
        deployment_decision = compute_deployment_decision(
            stage=deployment_stage,
            drift_kelly_multiplier=drift_multiplier,
            deployment_capital_multiplier=deployment_multiplier,
            pause_new_entries=pause_new_entries,
            delayed_quotes_detected=bool(broker_truth_snapshot.delayed_quotes_detected) if broker_truth_snapshot else False,
            request_budget_breached=bool(broker_truth_snapshot.request_budget_breached) if broker_truth_snapshot else False,
            duplicate_order_detected=duplicate_order_detected,
        )
        effective_capital_multiplier = deployment_decision.capital_multiplier
        stage_multiplier = effective_capital_multiplier / max(1e-9, drift_multiplier * deployment_multiplier) if (
            drift_multiplier > 0 and deployment_multiplier > 0
        ) else 0.0

        style_decision = choose_execution_style(
            candidate=candidate,
            adjusted_edge=execution_adjusted_edge,
            recent_order_requests_per_minute=effective_recent_rpm,
            order_request_budget_per_minute=order_request_budget_per_minute,
        )
        style_adjusted_edge = (
            execution_adjusted_edge
            - style_decision.request_budget_penalty
            - style_decision.cancel_replace_race_penalty
        )
        if policy_state:
            policy_action, _policy_scores = choose_entry_action(
                allowed_actions=("skip", style_decision.style),
                baseline_action=style_decision.style,
                policy_state=policy_state,
                min_confirmed_samples=policy_min_confirmed_samples,
            )
        else:
            policy_action = style_decision.style
        if policy_action == "skip":
            policy_reasons.append("policy_skip")
            style_adjusted_edge = min(0.0, style_adjusted_edge)

        latency_observation = metadata.get("latency_observation")
        if not isinstance(latency_observation, dict):
            latency_observation = metadata
        latency_profile = build_latency_profile(latency_observation)
        latency_penalty = estimate_latency_penalty(latency_profile)
        latency_blocked, latency_reasons = latency_kill_switch(
            latency_profile,
            max_quote_age_ms=max_quote_age_ms,
            max_decision_ms=max_decision_ms,
            max_submit_to_ack_ms=max_submit_to_ack_ms,
        )

        risk_penalty = max(
            0.0,
            float(metadata.get("pre_trade_risk_penalty") or metadata.get("risk_penalty") or 0.0),
        )
        risk_penalty += latency_penalty

        if require_broker_truth_clean and broker_truth_snapshot is not None:
            if broker_truth_snapshot.delayed_quotes_detected:
                broker_reasons.append("broker_delayed_quotes_detected")
                risk_penalty += 0.01
                hard_block = True
            if broker_truth_snapshot.request_budget_breached:
                broker_reasons.append("broker_request_budget_breached")
                risk_penalty += 0.005
                hard_block = True
            client_order_id = str(metadata.get("client_order_id") or "").strip()
            if client_order_id and client_order_id in duplicate_client_ids:
                broker_reasons.append("duplicate_client_order_id_detected")
                risk_penalty += 0.02
                hard_block = True
            order_signature = str(metadata.get("order_signature") or "").strip()
            if order_signature and order_signature in duplicate_signatures:
                broker_reasons.append("duplicate_order_signature_detected")
                risk_penalty += 0.02
                hard_block = True

        risk_adjusted_edge = style_adjusted_edge - risk_penalty
        if hard_block or latency_blocked or deployment_decision.paused:
            risk_adjusted_edge = min(0.0, risk_adjusted_edge)

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
        kelly_used *= effective_capital_multiplier

        if (
            risk_adjusted_edge <= 0
            or not passes_gate
            or hard_block
            or latency_blocked
            or deployment_decision.paused
            or policy_action == "skip"
        ):
            kelly_used = 0.0
        target_notional = notional_from_fraction(bankroll=bankroll, fraction=kelly_used)
        expected_holding_minutes = float(candidate.metadata.get("expected_holding_minutes") or 60.0)
        expected_holding_minutes = max(1.0, expected_holding_minutes)
        capital_minutes = max(1.0, target_notional * expected_holding_minutes)
        alpha_density = (
            max(0.0, risk_adjusted_edge) * max(0.0, expected_fill_probability) / capital_minutes
        )

        gate_reasons = list(reasons)
        gate_reasons.extend(broker_reasons)
        gate_reasons.extend(policy_reasons)
        gate_reasons.extend(latency_reasons)
        gate_reasons.extend(list(deployment_decision.reasons))
        if live_cap_penalty > 0:
            gate_reasons.append("live_prior_size_cap_applied")
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
        if hard_block:
            gate_reasons.append("hard_risk_block")
        if deployment_decision.paused:
            gate_reasons.append("deployment_paused")
        if effective_capital_multiplier <= 0.0:
            gate_reasons.append("drift_guard_paused")

        gate_reasons = _dedupe_reasons(gate_reasons)

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
                expected_fill_probability=round(expected_fill_probability, 6),
                slippage_p95_penalty=round(edge.slippage_p95_penalty, 6),
                post_fill_alpha_decay_penalty=round(edge.post_fill_alpha_decay_penalty, 6),
                uncertainty_penalty=round(edge.uncertainty_penalty, 6),
                execution_penalty=round(
                    edge.execution_penalty
                    + live_cap_penalty
                    + style_decision.request_budget_penalty
                    + style_decision.cancel_replace_race_penalty,
                    6,
                ),
                model_error_score=round(edge.model_error_score, 6),
                alpha_density=round(alpha_density, 10),
                execution_style=style_decision.style,
                policy_action=policy_action,
                deployment_stage=deployment_stage,
                expected_replace_count=max(0, int(style_decision.expected_replace_count)),
                live_prior_cap_penalty=round(live_cap_penalty, 6),
                request_budget_penalty=round(style_decision.request_budget_penalty, 6),
                cancel_replace_race_penalty=round(style_decision.cancel_replace_race_penalty, 6),
                drift_kelly_multiplier=round(drift_multiplier, 6),
                stage_capital_multiplier=round(stage_multiplier, 6),
                deployment_capital_multiplier=round(deployment_multiplier, 6),
                effective_capital_multiplier=round(effective_capital_multiplier, 6),
                latency_penalty=round(latency_penalty, 6),
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
                "policy_action": row.policy_action,
                "deployment_stage": row.deployment_stage,
                "expected_replace_count": row.expected_replace_count,
                "live_prior_cap_penalty": row.live_prior_cap_penalty,
                "request_budget_penalty": row.request_budget_penalty,
                "cancel_replace_race_penalty": row.cancel_replace_race_penalty,
                "drift_kelly_multiplier": row.drift_kelly_multiplier,
                "stage_capital_multiplier": row.stage_capital_multiplier,
                "deployment_capital_multiplier": row.deployment_capital_multiplier,
                "effective_capital_multiplier": row.effective_capital_multiplier,
                "latency_penalty": row.latency_penalty,
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
