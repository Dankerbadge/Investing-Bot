from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BucketPromotionMetrics:
    live_samples: int = 0
    lower_confidence_alpha_density: float = 0.0
    fill_brier_score: float = 0.0
    slippage_p75: float = 0.0
    broker_disagreement_rate: float = 0.0
    request_budget_breach_rate: float = 0.0
    delayed_quote_rate: float = 0.0
    # Disabled -> shadow readiness
    sessions_without_delayed_quotes: int = 0
    stream_gap_p99_seconds: float = 0.0
    peak_order_budget_utilization: float = 0.0
    unresolved_broker_mismatches: int = 0
    # Shadow -> probe readiness
    shadow_opportunities: int = 0
    shadow_would_trade_count: int = 0
    shadow_alpha_density_p25: float = 0.0
    median_predicted_fill_probability: float = 0.0
    hard_kills_last_5_sessions: int = 0
    # Probe/scaled readiness
    reconciled_round_trips: int = 0
    fill_calibration_abs_error: float = 0.0
    modeled_slippage_p75: float = 0.0
    prevailing_spread: float = 0.0
    unresolved_duplicate_order_incidents: int = 0
    request_budget_breaches_last_10_sessions: int = 0
    latency_hard_kills_last_10_sessions: int = 0
    broker_truth_mismatch_changes_pnl: bool = False
    broker_confirmed_exits: int = 0
    rolling20_alpha_density_lcb: float = 0.0
    rolling20_fill_calibration_abs_error: float = 0.0
    rolling20_slippage_p75: float = 0.0
    rolling20_modeled_slippage_p75: float = 0.0
    rolling20_spread: float = 0.0
    rolling20_latency_hard_kills: int = 0
    event_context_coverage: float = 1.0
    regime_context_coverage: float = 1.0


@dataclass(frozen=True)
class PromotionPolicy:
    min_sessions_without_delayed_quotes_for_shadow: int = 3
    max_stream_gap_p99_seconds_for_shadow: float = 5.0
    max_peak_order_budget_utilization_for_shadow: float = 0.50
    max_unresolved_broker_mismatches_for_shadow: int = 0
    min_shadow_opportunities_for_probe: int = 150
    min_shadow_would_trade_for_probe: int = 40
    min_shadow_alpha_density_p25_for_probe: float = 0.0
    min_median_predicted_fill_probability_for_probe: float = 0.35
    max_hard_kills_last_5_sessions_for_probe: int = 0
    min_reconciled_round_trips_for_scale: int = 30
    min_alpha_density_lcb_for_scale: float = 0.0
    max_fill_calibration_abs_error_for_scale: float = 0.10
    max_unresolved_duplicate_order_incidents_for_scale: int = 0
    max_request_budget_breaches_last_10_for_scale: int = 0
    max_latency_hard_kills_last_10_for_scale: int = 0
    max_slippage_worse_than_modeled_as_spread_fraction: float = 0.10
    min_event_context_coverage_for_scale: float = 0.70
    min_regime_context_coverage_for_scale: float = 0.70
    scale_step_confirmed_exit_interval: int = 50
    max_failure_count_rolling20_before_demotion: int = 2
    max_fill_calibration_abs_error_rolling20: float = 0.15
    max_slippage_worse_than_modeled_as_spread_fraction_rolling20: float = 0.25


def stage_capital_multiplier(stage: str) -> float:
    stage_norm = str(stage or "").strip().lower()
    return {
        "disabled": 0.0,
        "shadow": 0.0,
        "probe": 0.05,
        "scaled": 0.10,
        "scaled_1": 0.10,
        "scaled_2": 0.15,
        "scaled_3": 0.25,
        "mature": 0.25,
    }.get(stage_norm, 0.10 if stage_norm.startswith("scaled") else 0.0)


def _slippage_ceiling(modeled_slippage_p75: float, spread: float, spread_fraction: float) -> float:
    modeled = max(0.0, float(modeled_slippage_p75))
    spr = max(0.0, float(spread))
    return modeled + (spr * max(0.0, float(spread_fraction)))


def evaluate_stage_transition(
    *,
    current_stage: str,
    metrics: BucketPromotionMetrics,
    capability_verified: bool,
    policy: PromotionPolicy | None = None,
) -> tuple[str, str]:
    cfg = policy or PromotionPolicy()
    stage = str(current_stage or "").strip().lower() or "disabled"

    if not capability_verified:
        return "disabled", "capability_not_verified"

    if stage == "disabled":
        can_promote_to_shadow = (
            metrics.sessions_without_delayed_quotes >= cfg.min_sessions_without_delayed_quotes_for_shadow
            and metrics.stream_gap_p99_seconds < cfg.max_stream_gap_p99_seconds_for_shadow
            and metrics.peak_order_budget_utilization < cfg.max_peak_order_budget_utilization_for_shadow
            and metrics.unresolved_broker_mismatches <= cfg.max_unresolved_broker_mismatches_for_shadow
        )
        if can_promote_to_shadow:
            return "shadow", "shadow_threshold_met"
        return "disabled", "awaiting_shadow_thresholds"

    if stage == "shadow":
        can_promote_to_probe = (
            metrics.shadow_opportunities >= cfg.min_shadow_opportunities_for_probe
            and metrics.shadow_would_trade_count >= cfg.min_shadow_would_trade_for_probe
            and metrics.shadow_alpha_density_p25 > cfg.min_shadow_alpha_density_p25_for_probe
            and metrics.median_predicted_fill_probability >= cfg.min_median_predicted_fill_probability_for_probe
            and metrics.hard_kills_last_5_sessions <= cfg.max_hard_kills_last_5_sessions_for_probe
        )
        if can_promote_to_probe:
            return "probe", "probe_threshold_met"
        return "shadow", "awaiting_probe_thresholds"

    if stage in {"probe", "scaled", "scaled_1", "scaled_2", "scaled_3", "mature"}:
        slippage_limit = _slippage_ceiling(
            metrics.modeled_slippage_p75,
            metrics.prevailing_spread,
            cfg.max_slippage_worse_than_modeled_as_spread_fraction,
        )
        can_scale = (
            metrics.reconciled_round_trips >= cfg.min_reconciled_round_trips_for_scale
            and metrics.lower_confidence_alpha_density > cfg.min_alpha_density_lcb_for_scale
            and metrics.fill_calibration_abs_error <= cfg.max_fill_calibration_abs_error_for_scale
            and metrics.slippage_p75 <= slippage_limit
            and metrics.unresolved_duplicate_order_incidents <= cfg.max_unresolved_duplicate_order_incidents_for_scale
            and metrics.request_budget_breaches_last_10_sessions <= cfg.max_request_budget_breaches_last_10_for_scale
            and metrics.latency_hard_kills_last_10_sessions <= cfg.max_latency_hard_kills_last_10_for_scale
            and metrics.event_context_coverage >= cfg.min_event_context_coverage_for_scale
            and metrics.regime_context_coverage >= cfg.min_regime_context_coverage_for_scale
        )
        if stage == "probe":
            if can_scale:
                return "scaled_1", "scale_threshold_met"
            return "probe", "awaiting_scale_thresholds"

        rolling20_slippage_limit = _slippage_ceiling(
            metrics.rolling20_modeled_slippage_p75,
            metrics.rolling20_spread,
            cfg.max_slippage_worse_than_modeled_as_spread_fraction_rolling20,
        )
        failure_count = 0
        if metrics.rolling20_alpha_density_lcb <= 0.0:
            failure_count += 1
        if metrics.rolling20_fill_calibration_abs_error > cfg.max_fill_calibration_abs_error_rolling20:
            failure_count += 1
        if metrics.rolling20_slippage_p75 > rolling20_slippage_limit:
            failure_count += 1
        if metrics.rolling20_latency_hard_kills > 0:
            failure_count += 1

        if metrics.broker_truth_mismatch_changes_pnl:
            return "probe", "broker_truth_mismatch_demotion"
        if failure_count >= cfg.max_failure_count_rolling20_before_demotion:
            return "probe", "rolling20_failure_demotion"
        if not can_scale:
            return "probe", "scaled_drift_detected"

        if stage == "mature":
            return "mature", "within_mature_thresholds"

        stage_order = ["scaled_1", "scaled_2", "scaled_3", "mature"]
        normalized_stage = "scaled_1" if stage == "scaled" else stage
        if normalized_stage not in stage_order:
            normalized_stage = "scaled_1"
        idx = stage_order.index(normalized_stage)
        next_idx = min(len(stage_order) - 1, idx + (metrics.broker_confirmed_exits // cfg.scale_step_confirmed_exit_interval))
        next_stage = stage_order[next_idx]
        if next_stage != normalized_stage:
            return next_stage, "scaled_step_up"
        return normalized_stage, "within_scaled_thresholds"

    return "shadow", "unknown_stage_fallback"
