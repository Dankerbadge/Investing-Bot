from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

DEFAULT_BASELINES: tuple[str, ...] = (
    "cross_now",
    "passive_touch",
    "fixed_vertical",
    "skip",
)


@dataclass(frozen=True)
class BaselinePerformance:
    baseline: str
    sample_count: int
    mean_reward: float
    lcb95: float
    ucb95: float
    win_rate: float


@dataclass(frozen=True)
class BaselineComparison:
    baseline: str
    sample_count: int
    live_mean_reward: float
    baseline_mean_reward: float
    delta_mean_reward: float
    delta_lcb95: float


@dataclass(frozen=True)
class BaselineSuite:
    live: BaselinePerformance
    baselines: tuple[BaselinePerformance, ...]
    comparisons: tuple[BaselineComparison, ...]


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


def _mean_lcb_ucb(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return mean, mean, mean
    variance = sum((value - mean) ** 2 for value in values) / max(1, n - 1)
    stderr = sqrt(max(0.0, variance) / n)
    margin = 1.96 * stderr
    return mean, mean - margin, mean + margin


def _pnl_to_reward(row: dict[str, Any], pnl: float, *, reward_key: str) -> float:
    if str(reward_key).strip().lower() == "realized_pnl":
        return pnl
    notional = max(0.0, _as_float(row.get("target_notional"), 0.0))
    if notional > 0:
        return pnl / notional
    return pnl


def _baseline_reward(row: dict[str, Any], baseline: str, *, reward_key: str) -> float:
    base = str(baseline or "").strip().lower()

    explicit_key_map = {
        "cross_now": (
            "cross_now_reward",
            "cross_now_alpha_density",
            "counterfactual_cross_now_alpha_density",
            "crossed_now_alpha_density",
        ),
        "passive_touch": (
            "passive_touch_reward",
            "passive_touch_alpha_density",
            "counterfactual_passive_touch_alpha_density",
            "worked_passive_alpha_density",
        ),
        "fixed_vertical": (
            "fixed_vertical_reward",
            "fixed_vertical_alpha_density",
            "counterfactual_fixed_vertical_alpha_density",
        ),
        "skip": (
            "skip_reward",
            "skip_alpha_density",
            "counterfactual_skip_alpha_density",
            "skipped_alpha_density",
        ),
    }

    for key in explicit_key_map.get(base, ()):  # reward-like fields first
        if key in row:
            return _as_float(row.get(key), 0.0)

    pnl_key_map = {
        "cross_now": ("crossed_now_pnl", "counterfactual_cross_now_pnl"),
        "passive_touch": ("worked_passive_pnl", "counterfactual_passive_touch_pnl"),
        "fixed_vertical": ("fixed_vertical_pnl", "counterfactual_fixed_vertical_pnl"),
        "skip": ("skipped_pnl", "counterfactual_skip_pnl"),
    }
    for key in pnl_key_map.get(base, ()):  # fallback through pnl fields
        if key in row:
            pnl = _as_float(row.get(key), 0.0)
            return _pnl_to_reward(row, pnl, reward_key=reward_key)

    # Conservative fallback when baseline field is missing.
    if base == "skip":
        return 0.0
    return _as_float(row.get(reward_key), 0.0)


def _collect_rows(
    rows: list[dict[str, Any]],
    *,
    broker_confirmed_only: bool,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if broker_confirmed_only and not bool(row.get("broker_confirmed", True)):
            continue
        filtered.append(row)
    return filtered


def evaluate_baseline_performance(
    rows: list[dict[str, Any]],
    *,
    baseline: str,
    reward_key: str = "realized_alpha_density",
    broker_confirmed_only: bool = True,
) -> BaselinePerformance:
    filtered = _collect_rows(rows, broker_confirmed_only=broker_confirmed_only)
    rewards = [_baseline_reward(row, baseline, reward_key=reward_key) for row in filtered]
    mean, lcb, ucb = _mean_lcb_ucb(rewards)
    wins = sum(1 for value in rewards if value > 0)
    n = len(rewards)

    return BaselinePerformance(
        baseline=str(baseline or "").strip().lower() or "unknown",
        sample_count=n,
        mean_reward=round(mean, 12),
        lcb95=round(lcb, 12),
        ucb95=round(ucb, 12),
        win_rate=round((wins / n) if n else 0.0, 6),
    )


def compare_to_baselines(
    rows: list[dict[str, Any]],
    *,
    baseline_names: tuple[str, ...] | list[str] = DEFAULT_BASELINES,
    reward_key: str = "realized_alpha_density",
    broker_confirmed_only: bool = True,
) -> BaselineSuite:
    filtered = _collect_rows(rows, broker_confirmed_only=broker_confirmed_only)
    live_rewards = [_as_float(row.get(reward_key), 0.0) for row in filtered]
    live_mean, live_lcb, live_ucb = _mean_lcb_ucb(live_rewards)
    live_wins = sum(1 for value in live_rewards if value > 0)
    live = BaselinePerformance(
        baseline="live",
        sample_count=len(live_rewards),
        mean_reward=round(live_mean, 12),
        lcb95=round(live_lcb, 12),
        ucb95=round(live_ucb, 12),
        win_rate=round((live_wins / len(live_rewards)) if live_rewards else 0.0, 6),
    )

    baselines: list[BaselinePerformance] = []
    comparisons: list[BaselineComparison] = []
    for name in baseline_names:
        perf = evaluate_baseline_performance(
            filtered,
            baseline=name,
            reward_key=reward_key,
            broker_confirmed_only=False,  # already filtered
        )
        baselines.append(perf)
        delta = live.mean_reward - perf.mean_reward
        delta_lcb = live.lcb95 - perf.ucb95
        comparisons.append(
            BaselineComparison(
                baseline=perf.baseline,
                sample_count=min(live.sample_count, perf.sample_count),
                live_mean_reward=live.mean_reward,
                baseline_mean_reward=perf.mean_reward,
                delta_mean_reward=round(delta, 12),
                delta_lcb95=round(delta_lcb, 12),
            )
        )

    return BaselineSuite(
        live=live,
        baselines=tuple(baselines),
        comparisons=tuple(sorted(comparisons, key=lambda row: row.delta_mean_reward, reverse=True)),
    )
