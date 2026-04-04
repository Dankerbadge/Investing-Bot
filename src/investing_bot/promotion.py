from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BucketPromotionMetrics:
    live_samples: int
    lower_confidence_alpha_density: float
    fill_brier_score: float
    slippage_p75: float
    broker_disagreement_rate: float
    request_budget_breach_rate: float
    delayed_quote_rate: float


@dataclass(frozen=True)
class PromotionPolicy:
    min_samples_for_probe: int = 20
    min_samples_for_scale: int = 80
    max_fill_brier_for_scale: float = 0.20
    max_slippage_p75_for_scale: float = 0.02
    max_broker_disagreement_for_scale: float = 0.01
    max_budget_breach_for_scale: float = 0.01
    max_delayed_quote_for_scale: float = 0.01
    hard_broker_disagreement: float = 0.03
    hard_budget_breach: float = 0.03
    hard_delayed_quote: float = 0.05


def stage_capital_multiplier(stage: str) -> float:
    stage_norm = str(stage or "").strip().lower()
    return {
        "disabled": 0.0,
        "shadow": 0.0,
        "probe": 0.10,
        "scaled": 1.0,
    }.get(stage_norm, 0.0)


def evaluate_stage_transition(
    *,
    current_stage: str,
    metrics: BucketPromotionMetrics,
    capability_verified: bool,
    policy: PromotionPolicy | None = None,
) -> tuple[str, str]:
    cfg = policy or PromotionPolicy()
    stage = str(current_stage or "").strip().lower() or "disabled"

    hard_failure = (
        metrics.broker_disagreement_rate > cfg.hard_broker_disagreement
        or metrics.request_budget_breach_rate > cfg.hard_budget_breach
        or metrics.delayed_quote_rate > cfg.hard_delayed_quote
    )
    if hard_failure:
        return "shadow", "hard_drift_failure"

    if not capability_verified:
        return "disabled", "capability_not_verified"

    if stage == "disabled":
        return "shadow", "capability_verified"

    if stage == "shadow":
        if metrics.live_samples >= cfg.min_samples_for_probe:
            return "probe", "probe_threshold_met"
        return "shadow", "insufficient_samples_for_probe"

    if stage == "probe":
        can_scale = (
            metrics.live_samples >= cfg.min_samples_for_scale
            and metrics.lower_confidence_alpha_density > 0.0
            and metrics.fill_brier_score <= cfg.max_fill_brier_for_scale
            and metrics.slippage_p75 <= cfg.max_slippage_p75_for_scale
            and metrics.broker_disagreement_rate <= cfg.max_broker_disagreement_for_scale
            and metrics.request_budget_breach_rate <= cfg.max_budget_breach_for_scale
            and metrics.delayed_quote_rate <= cfg.max_delayed_quote_for_scale
        )
        if can_scale:
            return "scaled", "scale_threshold_met"
        return "probe", "awaiting_scale_thresholds"

    if stage == "scaled":
        keep_scaled = (
            metrics.lower_confidence_alpha_density > 0.0
            and metrics.fill_brier_score <= cfg.max_fill_brier_for_scale
            and metrics.slippage_p75 <= cfg.max_slippage_p75_for_scale
            and metrics.broker_disagreement_rate <= cfg.max_broker_disagreement_for_scale
            and metrics.request_budget_breach_rate <= cfg.max_budget_breach_for_scale
            and metrics.delayed_quote_rate <= cfg.max_delayed_quote_for_scale
        )
        if keep_scaled:
            return "scaled", "within_scaled_thresholds"
        return "probe", "scaled_drift_detected"

    return "shadow", "unknown_stage_fallback"
