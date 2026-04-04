from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True)
class ExecutionStyleDecision:
    style: str
    request_budget_penalty: float
    cancel_replace_race_penalty: float
    expected_replace_count: int
    broker_truth_required: bool = True


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
    - native_walk_limit: broker-managed walk-limit behavior
    - synthetic_ladder: app-managed cancel/replace ladder
    - cross_now: immediate execution; highest spread cost
    """

    spread = float(candidate.spread_cost)
    quote_age = float(candidate.quote_age_seconds)
    fill_prob = float(candidate.fill_probability)
    confidence = float(candidate.confidence)
    metadata = candidate.metadata if isinstance(candidate.metadata, dict) else {}
    pressure = 0.0
    if order_request_budget_per_minute > 0:
        pressure = min(1.0, max(0.0, recent_order_requests_per_minute / order_request_budget_per_minute))

    quote_mode = str(metadata.get("quote_mode") or "").strip().lower()
    delayed_quotes = bool(metadata.get("quotes_delayed")) or quote_mode == "delayed"
    supports_native_walk = bool(metadata.get("supports_native_walk_limit")) and bool(
        metadata.get("is_stock_etf_option", True)
    )
    native_walk_verified = bool(metadata.get("native_walk_limit_api_verified"))
    in_regular_hours = bool(metadata.get("is_regular_trading_hours", True))
    allow_native_walk = bool(metadata.get("allow_native_walk_limit", True))
    allow_synthetic_ladder = bool(metadata.get("allow_synthetic_ladder", True))
    latency_degrading = bool(metadata.get("latency_degrading"))
    time_sensitive_boundary = bool(metadata.get("time_sensitive_boundary"))
    spread_percentile = float(metadata.get("spread_percentile") or 0.5)
    cancel_ack_p95_ms = float(metadata.get("cancel_ack_p95_ms") or 0.0)
    duplicate_incidents_last_5 = int(metadata.get("duplicate_order_incidents_last_5_sessions") or 0)
    budget_headroom = max(0.0, 1.0 - pressure)
    native_walk_confirmed_uses = int(metadata.get("native_walk_confirmed_uses") or 0)
    native_walk_alpha_density_lcb = float(metadata.get("native_walk_alpha_density_lcb") or 0.0)
    deployment_stage = str(metadata.get("deployment_stage") or "").strip().lower()
    stage_rank = {
        "probe": 0,
        "scaled": 1,
        "scaled_1": 1,
        "scaled_2": 2,
        "scaled_3": 3,
        "mature": 4,
    }.get(deployment_stage, 1)

    native_walk_maturity_ok = (native_walk_confirmed_uses >= 25 and native_walk_alpha_density_lcb > 0.0)

    if adjusted_edge <= 0:
        style = "passive_touch"
    elif (latency_degrading or time_sensitive_boundary) and spread_percentile <= 0.35:
        style = "cross_now"
    elif spread <= 0.01 and fill_prob >= 0.75 and quote_age <= 2.0:
        style = "passive_touch"
    elif spread <= 0.02 and fill_prob >= 0.55 and confidence >= 0.6:
        style = "passive_improve"
    elif spread <= 0.05 and fill_prob >= 0.45:
        if (
            supports_native_walk
            and native_walk_verified
            and in_regular_hours
            and not delayed_quotes
            and allow_native_walk
            and stage_rank >= 1
            and native_walk_maturity_ok
        ):
            style = "native_walk_limit"
        elif (
            allow_synthetic_ladder
            and budget_headroom > 0.50
            and (cancel_ack_p95_ms <= 0 or cancel_ack_p95_ms < 2500.0)
            and duplicate_incidents_last_5 == 0
        ):
            style = "synthetic_ladder"
        else:
            style = "passive_touch"
    else:
        style = "cross_now"

    request_penalty = pressure * 0.01
    race_penalty = pressure * 0.001
    expected_replace_count = 0

    # When request budget is near exhaustion, avoid churn-heavy paths.
    if pressure >= 0.85 and style in {"synthetic_ladder", "native_walk_limit"}:
        style = "cross_now"
    elif pressure >= 0.70 and style == "synthetic_ladder":
        style = "passive_touch"

    if style == "synthetic_ladder":
        request_penalty += 0.010 + pressure * 0.012
        race_penalty += 0.006 + pressure * 0.010
        expected_replace_count = 3 + int(round(pressure * 3))
    elif style == "native_walk_limit":
        # Broker-managed walk behavior still has request/race friction, but far lower than synthetic ladders.
        request_penalty += 0.004 + pressure * 0.004
        race_penalty += 0.002 + pressure * 0.004
        expected_replace_count = 1
    elif style == "passive_improve":
        request_penalty += 0.003 + pressure * 0.004
        race_penalty += 0.001 + pressure * 0.002
        expected_replace_count = 1
    elif style == "cross_now":
        request_penalty += 0.001
        race_penalty += 0.0005

    return ExecutionStyleDecision(
        style=style,
        request_budget_penalty=round(max(0.0, request_penalty), 6),
        cancel_replace_race_penalty=round(max(0.0, race_penalty), 6),
        expected_replace_count=max(0, expected_replace_count),
    )
