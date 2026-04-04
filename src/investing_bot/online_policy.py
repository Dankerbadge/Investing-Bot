from __future__ import annotations

from dataclasses import dataclass, field
from math import log, sqrt


@dataclass(frozen=True)
class OnlinePolicyArm:
    action: str
    attempts: int = 0
    broker_confirmed_attempts: int = 0
    cumulative_reward: float = 0.0


@dataclass
class OnlinePolicyState:
    arms: dict[str, OnlinePolicyArm] = field(default_factory=dict)


def _get_arm(state: OnlinePolicyState, action: str) -> OnlinePolicyArm:
    return state.arms.get(action, OnlinePolicyArm(action=action))


def choose_online_action(
    *,
    state: OnlinePolicyState,
    allowed_actions: tuple[str, ...],
    baseline_action: str,
    min_confirmed_samples: int = 20,
    event_risk_score: float = 0.0,
    regime_multiplier: float = 1.0,
) -> tuple[str, dict[str, float]]:
    actions = tuple(dict.fromkeys(str(action or "").strip() for action in allowed_actions if str(action or "").strip()))
    if not actions:
        return baseline_action, {baseline_action: 0.0}

    total_confirmed = sum(max(0, _get_arm(state, action).broker_confirmed_attempts) for action in actions)
    anchor = max(1, total_confirmed)
    event_risk = min(1.0, max(0.0, float(event_risk_score)))
    regime = min(1.0, max(0.0, float(regime_multiplier)))

    scores: dict[str, float] = {}
    for action in actions:
        arm = _get_arm(state, action)
        confirmed = max(0, int(arm.broker_confirmed_attempts))
        attempts = max(0, int(arm.attempts))
        mean_reward = (float(arm.cumulative_reward) / confirmed) if confirmed > 0 else 0.0
        exploration = sqrt((2.0 * log(anchor + 1.0)) / (confirmed + 1.0))

        score = mean_reward + min(0.2, exploration)
        if confirmed == 0 and action not in {baseline_action, "skip"}:
            score -= 0.20
        if confirmed < min_confirmed_samples and action != baseline_action:
            score -= 0.05
        if attempts < confirmed:
            score -= 0.05

        if action == "skip":
            score += event_risk * 0.15
            score += (1.0 - regime) * 0.12
        elif action != "passive_touch":
            score -= event_risk * 0.20
            score -= (1.0 - regime) * 0.20

        if action == baseline_action and confirmed >= min_confirmed_samples:
            score += 0.02

        scores[action] = round(score, 12)

    choice = max(scores.items(), key=lambda item: item[1])[0]
    return choice, scores


def update_online_policy(
    state: OnlinePolicyState,
    *,
    action: str,
    reward: float,
    broker_confirmed: bool,
) -> OnlinePolicyState:
    action_norm = str(action or "").strip()
    if not action_norm:
        return OnlinePolicyState(arms=dict(state.arms))

    current = dict(state.arms)
    previous = _get_arm(state, action_norm)
    attempts = previous.attempts + 1
    confirmed = previous.broker_confirmed_attempts + (1 if broker_confirmed else 0)
    cumulative = previous.cumulative_reward + (float(reward) if broker_confirmed else 0.0)

    current[action_norm] = OnlinePolicyArm(
        action=action_norm,
        attempts=attempts,
        broker_confirmed_attempts=confirmed,
        cumulative_reward=round(cumulative, 12),
    )
    return OnlinePolicyState(arms=current)
