from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True)
class ExecutionStyleDecision:
    style: str
    request_budget_penalty: float
    cancel_replace_race_penalty: float


def choose_execution_style(
    *,
    candidate: Candidate,
    adjusted_edge: float,
    recent_order_requests_per_minute: float,
    order_request_budget_per_minute: float = 120.0,
) -> ExecutionStyleDecision:
    """
    Select execution style and add penalties for budget pressure and change/cancel races.

    Styles:
    - passive_touch: quote at touch; lowest churn
    - passive_improve: inside spread/mid bias; moderate churn
    - cross_now: immediate execution; highest spread cost
    - walk_limit: staged cancel/replace ladder; high request and race risk
    """

    spread = float(candidate.spread_cost)
    quote_age = float(candidate.quote_age_seconds)
    fill_prob = float(candidate.fill_probability)
    confidence = float(candidate.confidence)
    pressure = 0.0
    if order_request_budget_per_minute > 0:
        pressure = min(1.0, max(0.0, recent_order_requests_per_minute / order_request_budget_per_minute))

    if adjusted_edge <= 0:
        style = "passive_touch"
    elif spread <= 0.01 and fill_prob >= 0.75 and quote_age <= 2.0:
        style = "passive_touch"
    elif spread <= 0.03 and fill_prob >= 0.60 and confidence >= 0.6:
        style = "passive_improve"
    elif spread <= 0.05 and fill_prob >= 0.45:
        style = "walk_limit"
    else:
        style = "cross_now"

    request_penalty = pressure * 0.01
    race_penalty = 0.0

    if style == "walk_limit":
        # walk-limit style implies repeated changes and race risk under throttle.
        request_penalty += 0.008 + pressure * 0.01
        race_penalty += 0.004 + pressure * 0.008
    elif style == "passive_improve":
        request_penalty += 0.003 + pressure * 0.004
        race_penalty += 0.001 + pressure * 0.002
    elif style == "cross_now":
        request_penalty += 0.001
        race_penalty += 0.0005

    return ExecutionStyleDecision(
        style=style,
        request_budget_penalty=round(max(0.0, request_penalty), 6),
        cancel_replace_race_penalty=round(max(0.0, race_penalty), 6),
    )
