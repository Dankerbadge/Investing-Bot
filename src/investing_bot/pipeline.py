from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .capital_efficiency import compute_capital_efficiency
from .corp_actions import (
    corporate_action_hard_block,
    corporate_action_penalty,
    corporate_action_reasons,
    infer_corporate_action_context,
)
from .deployment_control import compute_deployment_decision
from .event_context import event_context_penalty, infer_event_context
from .execution_learning import LearnedExecutionPrior, adjustments_for_candidate
from .execution_style import choose_execution_style
from .gating import LiquidityGate, evaluate_liquidity
from .instrument_registry import InstrumentRegistry
from .latency import build_latency_profile, estimate_latency_penalty, latency_kill_switch
from .models import Candidate, ScoredCandidate
from .policy import ActionPolicyStats, choose_entry_action
from .promotion import stage_capital_multiplier
from .regime import infer_regime_context, regime_penalty
from .reconciliation import BrokerTruthSnapshot
from .risk import ConcentrationLimits, select_concentrated_portfolio
from .ruin_guard import compute_ruin_guard
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
    instrument_registry: InstrumentRegistry | None = None,
    allow_adjusted_options: bool = False,
    allow_non_standard_expirations: bool = False,
    allow_undefined_risk: bool = False,
    require_broker_truth_clean: bool = True,
    max_quote_age_ms: float = 3000.0,
    max_decision_ms: float = 1200.0,
    max_submit_to_ack_ms: float = 5000.0,
    max_cancel_roundtrip_ms: float = 4000.0,
) -> dict[str, Any]:
    def _dedupe_reasons(items: list[str]) -> list[str]:
        deduped: list[str] = []
        for item in items:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _normalize_stage(stage_value: str) -> str:
        stage_text = str(stage_value or "").strip().lower()
        if not stage_text:
            return "scaled_1"
        if stage_text == "scaled":
            return "scaled_1"
        return stage_text

    def _per_trade_max_loss_fraction(stage_value: str, risk_class: str, broker_confirmed_exits: int) -> float:
        stage_norm = _normalize_stage(stage_value)
        cls = str(risk_class or "defined_risk_long_convexity").strip().lower()
        if cls == "naked_short_american_single_name":
            if int(broker_confirmed_exits) < 200:
                return 0.0
            return 0.001  # 0.10% NLV
        if cls in {"credit_spread_defined_risk", "short_premium_defined_risk"}:
            table = {
                "probe": 0.001,
                "scaled_1": 0.003,
                "scaled_2": 0.005,
                "scaled_3": 0.0075,
                "mature": 0.0075,
            }
            return table.get(stage_norm, 0.0)
        table = {
            "probe": 0.0015,
            "scaled_1": 0.005,
            "scaled_2": 0.0075,
            "scaled_3": 0.01,
            "mature": 0.01,
        }
        return table.get(stage_norm, 0.0)

    scored: list[ScoredCandidate] = []
    broker_observed_rpm = 0.0
    broker_budget_utilization = 0.0
    duplicate_client_ids: set[str] = set()
    duplicate_signatures: set[str] = set()
    if broker_truth_snapshot is not None:
        broker_observed_rpm = float(broker_truth_snapshot.observed_requests_per_minute)
        broker_budget_utilization = float(broker_truth_snapshot.request_budget_utilization)
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
        governance_reasons: list[str] = []
        hard_block = False
        deployment_stage = _normalize_stage(str(metadata.get("deployment_stage") or "scaled_1"))
        stream_gap_seconds = float(metadata.get("stream_gap_seconds") or 0.0)
        daily_pnl_fraction = float(metadata.get("daily_pnl_fraction") or 0.0)
        event_context = infer_event_context(metadata)
        regime_context = infer_regime_context(
            {
                "vix_level": metadata.get("vix_level"),
                "put_call_ratio": metadata.get("put_call_ratio"),
                "macro_regime": metadata.get("macro_regime"),
                "spread_cost": candidate.spread_cost,
            }
        )
        event_penalty = event_context_penalty(event_context)
        regime_penalty_value = regime_penalty(regime_context)

        deployment_decision = compute_deployment_decision(
            stage=deployment_stage,
            drift_kelly_multiplier=drift_multiplier,
            deployment_capital_multiplier=deployment_multiplier,
            pause_new_entries=pause_new_entries,
            order_budget_utilization=broker_budget_utilization,
            stream_gap_seconds=stream_gap_seconds,
            daily_pnl_fraction=daily_pnl_fraction,
            regime_multiplier=regime_context.risk_multiplier,
            event_risk_score=event_context.event_risk_score,
            delayed_quotes_detected=bool(broker_truth_snapshot.delayed_quotes_detected) if broker_truth_snapshot else False,
            request_budget_breached=bool(broker_truth_snapshot.request_budget_breached) if broker_truth_snapshot else False,
            duplicate_order_detected=duplicate_order_detected,
        )
        ruin_guard = compute_ruin_guard(
            drawdown_fraction=drawdown_fraction,
            daily_pnl_fraction=daily_pnl_fraction,
            realized_volatility=float(metadata.get("realized_volatility") or 0.0),
            rolling_loss_streak=int(metadata.get("rolling_loss_streak") or 0),
            stage=deployment_stage,
        )
        governance_reasons.extend(list(ruin_guard.reasons))
        effective_capital_multiplier = deployment_decision.capital_multiplier * ruin_guard.kelly_multiplier
        stage_multiplier = stage_capital_multiplier(deployment_stage)

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
                event_risk_score=event_context.event_risk_score,
                regime_multiplier=regime_context.risk_multiplier,
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
        illiquid_or_multileg = bool(metadata.get("illiquid_or_multileg")) or bool(metadata.get("is_multileg"))
        soft_quote_age_ms = 1500.0 if illiquid_or_multileg else 750.0
        hard_quote_age_ms = 2500.0 if illiquid_or_multileg else 1500.0
        soft_submit_to_ack_ms = 1500.0
        hard_submit_to_ack_ms = min(max_submit_to_ack_ms, 3000.0)
        soft_cancel_roundtrip_ms = 2500.0
        hard_cancel_roundtrip_ms = min(max_cancel_roundtrip_ms, 4000.0)
        if latency_profile.quote_age_ms > soft_quote_age_ms:
            latency_penalty += 0.004
        if latency_profile.submit_to_ack_ms > soft_submit_to_ack_ms:
            latency_penalty += 0.003
        if latency_profile.cancel_roundtrip_ms > soft_cancel_roundtrip_ms:
            latency_penalty += 0.002
        latency_blocked, latency_reasons = latency_kill_switch(
            latency_profile,
            max_quote_age_ms=min(max_quote_age_ms, hard_quote_age_ms),
            max_decision_ms=max_decision_ms,
            max_submit_to_ack_ms=hard_submit_to_ack_ms,
            max_cancel_roundtrip_ms=hard_cancel_roundtrip_ms,
        )

        risk_penalty = max(
            0.0,
            float(metadata.get("pre_trade_risk_penalty") or metadata.get("risk_penalty") or 0.0),
        )
        corp_context = infer_corporate_action_context({**metadata, "side": candidate.side})
        risk_penalty += corporate_action_penalty(corp_context)
        governance_reasons.extend(list(corporate_action_reasons(corp_context)))
        if corporate_action_hard_block(corp_context):
            hard_block = True
            if "assignment_risk_hard_limit" not in governance_reasons:
                governance_reasons.append("assignment_risk_hard_limit")

        if instrument_registry is not None:
            allowed, instrument_reasons = instrument_registry.evaluate_trade(
                symbol=candidate.ticker,
                allow_adjusted=allow_adjusted_options,
                allow_non_standard=allow_non_standard_expirations,
                allow_undefined_risk=allow_undefined_risk,
            )
            if not allowed:
                hard_block = True
                governance_reasons.extend(list(instrument_reasons))

        risk_penalty += latency_penalty + event_penalty + regime_penalty_value

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
        if hard_block or latency_blocked or deployment_decision.paused or ruin_guard.paused:
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
            or ruin_guard.paused
            or policy_action == "skip"
        ):
            kelly_used = 0.0
        target_notional = notional_from_fraction(bankroll=bankroll, fraction=kelly_used)

        # Stage-specific sizing caps from controlled-live policy.
        broker_confirmed_exits = int(metadata.get("broker_confirmed_exits") or 0)
        risk_class = str(metadata.get("risk_class") or "defined_risk_long_convexity")
        per_trade_max_loss_fraction = _per_trade_max_loss_fraction(
            deployment_stage,
            risk_class,
            broker_confirmed_exits,
        )
        per_trade_cap_notional = 0.0
        if per_trade_max_loss_fraction > 0.0:
            per_trade_cap_notional = (bankroll * per_trade_max_loss_fraction) / max(1.0, float(candidate.loss_multiple))
        if deployment_stage == "probe":
            contract_notional = float(metadata.get("contract_notional") or max(1.0, candidate.reference_price * 100.0))
            if per_trade_cap_notional > 0:
                per_trade_cap_notional = min(per_trade_cap_notional, contract_notional)
            else:
                per_trade_cap_notional = contract_notional
        if per_trade_cap_notional <= 0.0:
            kelly_used = 0.0
            target_notional = 0.0
        elif target_notional > per_trade_cap_notional:
            target_notional = round(per_trade_cap_notional, 2)
            kelly_used = min(kelly_used, max(0.0, target_notional / bankroll))

        expected_holding_minutes = float(candidate.metadata.get("expected_holding_minutes") or 60.0)
        expected_holding_minutes = max(1.0, expected_holding_minutes)
        efficiency = compute_capital_efficiency(
            expected_net_pnl=max(0.0, risk_adjusted_edge) * max(0.0, expected_fill_probability),
            notional=target_notional,
            expected_holding_minutes=expected_holding_minutes,
            incremental_max_loss=target_notional * max(1.0, float(candidate.loss_multiple)),
            incremental_shock_loss=target_notional * max(1.0, float(candidate.loss_multiple)),
        )
        alpha_density = efficiency.alpha_density

        gate_reasons = list(reasons)
        gate_reasons.extend(broker_reasons)
        gate_reasons.extend(policy_reasons)
        gate_reasons.extend(governance_reasons)
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
        if ruin_guard.paused:
            gate_reasons.append("ruin_guard_paused")
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
