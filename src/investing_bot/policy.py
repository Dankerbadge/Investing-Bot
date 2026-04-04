from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt


@dataclass(frozen=True)
class ActionPolicyStats:
    action: str
    attempts: int = 0
    positive_outcomes: int = 0
    cumulative_alpha_density: float = 0.0
    broker_confirmed_attempts: int = 0


def default_policy_actions() -> tuple[str, ...]:
    return (
        "skip",
        "passive_touch",
        "passive_improve",
        "cross_now",
        "synthetic_ladder",
        "native_walk_limit",
    )


def choose_entry_action(
    *,
    allowed_actions: tuple[str, ...],
    baseline_action: str,
    policy_state: dict[str, ActionPolicyStats] | None = None,
    min_confirmed_samples: int = 20,
) -> tuple[str, dict[str, float]]:
    """
    Deterministic UCB-style action chooser.
    - Uses broker-confirmed historical outcomes only.
    - Returns action + per-action scores for observability.
    """

    actions = tuple(dict.fromkeys(str(action or "").strip() for action in allowed_actions if str(action or "").strip()))
    if not actions:
        return baseline_action, {baseline_action: 0.0}

    state = policy_state or {}
    totals = sum(max(0, int(state.get(action, ActionPolicyStats(action=action)).broker_confirmed_attempts)) for action in actions)
    exploration_anchor = max(1, totals)

    scores: dict[str, float] = {}
    for action in actions:
        stats = state.get(action, ActionPolicyStats(action=action))
        confirmed = max(0, int(stats.broker_confirmed_attempts))
        attempts = max(0, int(stats.attempts))
        positive = max(0, int(stats.positive_outcomes))

        # Beta(1, 1) posterior mean for positive alpha outcomes.
        posterior_mean = (positive + 1.0) / (confirmed + 2.0)
        uncertainty_bonus = min(0.15, sqrt(2.0 * log(exploration_anchor + 1.0) / (confirmed + 1.0)))

        # If we have effectively no broker-confirmed evidence, prefer baseline over aggressive overrides.
        sparse_penalty = 0.05 if (confirmed < min_confirmed_samples and action != baseline_action and action != "skip") else 0.0
        cold_start_penalty = 0.25 if (confirmed == 0 and action != "skip") else 0.0
        # Skip requires stronger evidence before dominating.
        skip_penalty = 0.03 if action == "skip" and confirmed < min_confirmed_samples else 0.0
        # Lightly reward actions with larger confirmed alpha-density mean.
        mean_alpha_density = (stats.cumulative_alpha_density / confirmed) if confirmed > 0 else 0.0
        alpha_density_bonus = max(-0.02, min(0.02, mean_alpha_density * 100.0))

        score = (
            posterior_mean
            + uncertainty_bonus
            + alpha_density_bonus
            - sparse_penalty
            - cold_start_penalty
            - skip_penalty
        )
        # Slight tiebreak in favor of baseline.
        if action == baseline_action and confirmed >= min_confirmed_samples:
            score += 0.01
        # Require explicit enablement before native walk can dominate selection.
        if action == "native_walk_limit" and confirmed == 0:
            score -= 0.1

        # Guard against malformed states.
        if attempts < confirmed:
            score -= 0.02

        scores[action] = float(score)

    chosen = max(scores.items(), key=lambda item: item[1])[0]
    return chosen, scores


def update_entry_policy(
    state: dict[str, ActionPolicyStats] | None,
    *,
    action: str,
    realized_alpha_density: float,
    broker_confirmed: bool,
) -> dict[str, ActionPolicyStats]:
    """
    Update policy state with one realized sample.
    Only broker-confirmed outcomes are allowed to shape the policy.
    """

    action_norm = str(action or "").strip()
    if not action_norm:
        return dict(state or {})

    current = dict(state or {})
    previous = current.get(action_norm, ActionPolicyStats(action=action_norm))

    attempts = previous.attempts + 1
    confirmed_attempts = previous.broker_confirmed_attempts + (1 if broker_confirmed else 0)
    positive_outcomes = previous.positive_outcomes
    cumulative_alpha_density = previous.cumulative_alpha_density

    if broker_confirmed:
        if float(realized_alpha_density) > 0:
            positive_outcomes += 1
        cumulative_alpha_density += float(realized_alpha_density)

    current[action_norm] = ActionPolicyStats(
        action=action_norm,
        attempts=attempts,
        positive_outcomes=positive_outcomes,
        cumulative_alpha_density=round(cumulative_alpha_density, 12),
        broker_confirmed_attempts=confirmed_attempts,
    )
    return current
