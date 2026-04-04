from __future__ import annotations

from dataclasses import dataclass
from math import sqrt


@dataclass(frozen=True)
class SequentialTestState:
    sample_count: int = 0
    cumulative_reward: float = 0.0
    cumulative_squared_reward: float = 0.0
    positive_count: int = 0


def update_state(state: SequentialTestState, reward: float) -> SequentialTestState:
    value = float(reward)
    samples = state.sample_count + 1
    cumulative = state.cumulative_reward + value
    cumulative_sq = state.cumulative_squared_reward + (value * value)
    positives = state.positive_count + (1 if value > 0 else 0)
    return SequentialTestState(
        sample_count=samples,
        cumulative_reward=round(cumulative, 12),
        cumulative_squared_reward=round(cumulative_sq, 12),
        positive_count=positives,
    )


def posterior_mean(state: SequentialTestState) -> float:
    if state.sample_count <= 0:
        return 0.0
    return state.cumulative_reward / state.sample_count


def posterior_variance(state: SequentialTestState) -> float:
    if state.sample_count <= 1:
        return 0.0
    mean = posterior_mean(state)
    raw = (state.cumulative_squared_reward / state.sample_count) - (mean * mean)
    return max(0.0, raw)


def lower_confidence_bound(state: SequentialTestState, z_value: float = 1.96) -> float:
    if state.sample_count <= 0:
        return 0.0
    mean = posterior_mean(state)
    variance = posterior_variance(state)
    stderr = sqrt(variance / state.sample_count) if state.sample_count > 0 else 0.0
    return mean - (abs(float(z_value)) * stderr)


def upper_confidence_bound(state: SequentialTestState, z_value: float = 1.96) -> float:
    if state.sample_count <= 0:
        return 0.0
    mean = posterior_mean(state)
    variance = posterior_variance(state)
    stderr = sqrt(variance / state.sample_count) if state.sample_count > 0 else 0.0
    return mean + (abs(float(z_value)) * stderr)


def success_rate(state: SequentialTestState) -> float:
    if state.sample_count <= 0:
        return 0.0
    return state.positive_count / state.sample_count


def should_promote_alpha(
    *,
    state: SequentialTestState,
    min_samples: int,
    min_lcb: float,
    min_success_rate: float = 0.50,
) -> bool:
    if state.sample_count < max(1, int(min_samples)):
        return False
    if success_rate(state) < float(min_success_rate):
        return False
    return lower_confidence_bound(state) > float(min_lcb)


def should_kill_alpha(
    *,
    state: SequentialTestState,
    min_samples: int,
    max_ucb: float,
) -> bool:
    if state.sample_count < max(1, int(min_samples)):
        return False
    return upper_confidence_bound(state) < float(max_ucb)
