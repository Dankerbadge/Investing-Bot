from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any


@dataclass(frozen=True)
class AblationScenario:
    name: str
    use_signal_arbiter: bool = True
    use_structure_selector: bool = True
    use_evidence_pool: bool = True
    use_event_regime_features: bool = True


@dataclass(frozen=True)
class AblationResult:
    scenario: str
    sample_count: int
    mean_reward: float
    lcb95: float
    ucb95: float
    win_rate: float


@dataclass(frozen=True)
class AblationStudy:
    results: tuple[AblationResult, ...]
    best_scenario: str


DEFAULT_ABLATION_SCENARIOS: tuple[AblationScenario, ...] = (
    AblationScenario(name="full_stack", use_signal_arbiter=True, use_structure_selector=True, use_evidence_pool=True, use_event_regime_features=True),
    AblationScenario(name="no_arbiter", use_signal_arbiter=False, use_structure_selector=True, use_evidence_pool=True, use_event_regime_features=True),
    AblationScenario(name="no_structure_selector", use_signal_arbiter=True, use_structure_selector=False, use_evidence_pool=True, use_event_regime_features=True),
    AblationScenario(name="no_evidence_pool", use_signal_arbiter=True, use_structure_selector=True, use_evidence_pool=False, use_event_regime_features=True),
    AblationScenario(name="no_event_regime", use_signal_arbiter=True, use_structure_selector=True, use_evidence_pool=True, use_event_regime_features=False),
    AblationScenario(name="minimal_controls", use_signal_arbiter=False, use_structure_selector=False, use_evidence_pool=False, use_event_regime_features=False),
)


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


def _feature_delta(row: dict[str, Any], feature: str) -> float:
    feature_key_map = {
        "signal_arbiter": (
            "signal_arbiter_delta_reward",
            "signal_arbiter_delta_alpha_density",
            "arbiter_delta_alpha_density",
        ),
        "structure_selector": (
            "structure_selector_delta_reward",
            "structure_selector_delta_alpha_density",
        ),
        "evidence_pool": (
            "evidence_pool_delta_reward",
            "evidence_pool_delta_alpha_density",
        ),
        "event_regime_features": (
            "event_regime_delta_reward",
            "event_regime_delta_alpha_density",
            "event_context_delta_alpha_density",
        ),
    }
    for key in feature_key_map.get(feature, ()):  # explicit deltas first
        if key in row:
            return _as_float(row.get(key), 0.0)

    if feature == "event_regime_features":
        # If explicit deltas are missing, use observed event/regime penalties as proxy.
        return _as_float(row.get("event_penalty"), 0.0) + _as_float(row.get("regime_penalty"), 0.0)

    return 0.0


def estimate_scenario_reward(
    row: dict[str, Any],
    scenario: AblationScenario,
    *,
    reward_key: str,
) -> float:
    reward = _as_float(row.get(reward_key), 0.0)

    if not scenario.use_signal_arbiter:
        reward -= _feature_delta(row, "signal_arbiter")
    if not scenario.use_structure_selector:
        reward -= _feature_delta(row, "structure_selector")
    if not scenario.use_evidence_pool:
        reward -= _feature_delta(row, "evidence_pool")
    if not scenario.use_event_regime_features:
        reward -= _feature_delta(row, "event_regime_features")

    return reward


def run_ablation_study(
    rows: list[dict[str, Any]],
    *,
    scenarios: tuple[AblationScenario, ...] | list[AblationScenario] = DEFAULT_ABLATION_SCENARIOS,
    reward_key: str = "realized_alpha_density",
    broker_confirmed_only: bool = True,
) -> AblationStudy:
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if broker_confirmed_only and not bool(row.get("broker_confirmed", True)):
            continue
        filtered.append(row)

    results: list[AblationResult] = []
    for scenario in scenarios:
        rewards = [estimate_scenario_reward(row, scenario, reward_key=reward_key) for row in filtered]
        mean, lcb, ucb = _mean_lcb_ucb(rewards)
        wins = sum(1 for value in rewards if value > 0)
        n = len(rewards)
        results.append(
            AblationResult(
                scenario=scenario.name,
                sample_count=n,
                mean_reward=round(mean, 12),
                lcb95=round(lcb, 12),
                ucb95=round(ucb, 12),
                win_rate=round((wins / n) if n else 0.0, 6),
            )
        )

    ranked = sorted(results, key=lambda row: (row.mean_reward, row.lcb95, row.sample_count, row.scenario), reverse=True)
    best = ranked[0].scenario if ranked else "none"
    return AblationStudy(results=tuple(ranked), best_scenario=best)
