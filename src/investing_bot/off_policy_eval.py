from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from typing import Any

from .experiment_registry import ExperimentRegistry


@dataclass(frozen=True)
class OffPolicyEstimate:
    method: str
    sample_count: int
    effective_sample_size: float
    mean: float
    lcb95: float
    ucb95: float


@dataclass(frozen=True)
class PromotionReport:
    challenger: str
    champion: str
    promote: bool
    reason: str
    ips: OffPolicyEstimate
    doubly_robust: OffPolicyEstimate


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _mean_lcb_ucb(samples: list[float]) -> tuple[float, float, float]:
    if not samples:
        return 0.0, 0.0, 0.0
    n = len(samples)
    mean = sum(samples) / n
    if n == 1:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in samples) / max(1, n - 1)
    std_err = sqrt(max(0.0, variance) / n)
    margin = 1.96 * std_err
    return mean, mean - margin, mean + margin


def log_propensity(
    *,
    registry: ExperimentRegistry,
    decision_payload: dict[str, Any],
    policy_version: str,
    config: dict[str, Any],
    features: dict[str, Any],
    behavior_propensity: float,
    target_propensity: float,
    predicted_reward: float = 0.0,
    source: str = "live",
) -> Path:
    payload = dict(decision_payload)
    payload["behavior_propensity"] = round(max(0.0, min(1.0, float(behavior_propensity))), 8)
    payload["target_propensity"] = round(max(0.0, min(1.0, float(target_propensity))), 8)
    payload["predicted_reward"] = round(float(predicted_reward), 12)
    return registry.record_decision(
        decision_payload=payload,
        policy_version=policy_version,
        config=config,
        features=features,
        source=source,
    )


def evaluate_challenger_ips(
    rows: list[dict[str, Any]],
    *,
    reward_key: str = "realized_alpha_density",
    behavior_propensity_key: str = "behavior_propensity",
    target_propensity_key: str = "target_propensity",
    max_weight: float = 20.0,
) -> OffPolicyEstimate:
    weighted_rewards: list[float] = []
    weights: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        reward = _as_float(row.get(reward_key), default=0.0)
        behavior = _as_float(row.get(behavior_propensity_key), default=0.0)
        target = _as_float(row.get(target_propensity_key), default=0.0)
        if behavior <= 0.0 or target < 0.0:
            continue
        weight = min(float(max_weight), max(0.0, target / behavior))
        weighted_rewards.append(weight * reward)
        weights.append(weight)

    if not weights:
        return OffPolicyEstimate(method="ips", sample_count=0, effective_sample_size=0.0, mean=0.0, lcb95=0.0, ucb95=0.0)

    sum_w = sum(weights)
    estimate_samples = [value / sum_w for value in weighted_rewards]
    mean, lcb, ucb = _mean_lcb_ucb(estimate_samples)
    ess = (sum_w * sum_w) / max(1e-12, sum(weight * weight for weight in weights))

    return OffPolicyEstimate(
        method="ips",
        sample_count=len(weights),
        effective_sample_size=round(ess, 6),
        mean=round(mean, 12),
        lcb95=round(lcb, 12),
        ucb95=round(ucb, 12),
    )


def evaluate_challenger_dr(
    rows: list[dict[str, Any]],
    *,
    reward_key: str = "realized_alpha_density",
    behavior_propensity_key: str = "behavior_propensity",
    target_propensity_key: str = "target_propensity",
    predicted_reward_key: str = "predicted_reward",
    max_weight: float = 20.0,
) -> OffPolicyEstimate:
    dr_samples: list[float] = []
    weights: list[float] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        reward = _as_float(row.get(reward_key), default=0.0)
        behavior = _as_float(row.get(behavior_propensity_key), default=0.0)
        target = _as_float(row.get(target_propensity_key), default=0.0)
        q_hat = _as_float(row.get(predicted_reward_key), default=0.0)
        if behavior <= 0.0 or target < 0.0:
            continue

        weight = min(float(max_weight), max(0.0, target / behavior))
        dr = q_hat + (weight * (reward - q_hat))
        dr_samples.append(dr)
        weights.append(weight)

    if not dr_samples:
        return OffPolicyEstimate(method="dr", sample_count=0, effective_sample_size=0.0, mean=0.0, lcb95=0.0, ucb95=0.0)

    mean, lcb, ucb = _mean_lcb_ucb(dr_samples)
    sum_w = sum(weights)
    ess = (sum_w * sum_w) / max(1e-12, sum(weight * weight for weight in weights))
    return OffPolicyEstimate(
        method="dr",
        sample_count=len(dr_samples),
        effective_sample_size=round(ess, 6),
        mean=round(mean, 12),
        lcb95=round(lcb, 12),
        ucb95=round(ucb, 12),
    )


def promotion_report(
    *,
    champion: str,
    challenger: str,
    ips: OffPolicyEstimate,
    doubly_robust: OffPolicyEstimate,
    min_effective_sample_size: float = 30.0,
    min_lcb95: float = 0.0,
) -> PromotionReport:
    if ips.effective_sample_size < float(min_effective_sample_size):
        return PromotionReport(
            challenger=challenger,
            champion=champion,
            promote=False,
            reason="insufficient_ips_sample_size",
            ips=ips,
            doubly_robust=doubly_robust,
        )

    if doubly_robust.effective_sample_size < float(min_effective_sample_size):
        return PromotionReport(
            challenger=challenger,
            champion=champion,
            promote=False,
            reason="insufficient_dr_sample_size",
            ips=ips,
            doubly_robust=doubly_robust,
        )

    if ips.lcb95 > float(min_lcb95) and doubly_robust.lcb95 > float(min_lcb95):
        return PromotionReport(
            challenger=challenger,
            champion=champion,
            promote=True,
            reason="challenger_off_policy_positive_lcb",
            ips=ips,
            doubly_robust=doubly_robust,
        )

    return PromotionReport(
        challenger=challenger,
        champion=champion,
        promote=False,
        reason="challenger_lcb_not_positive",
        ips=ips,
        doubly_robust=doubly_robust,
    )
