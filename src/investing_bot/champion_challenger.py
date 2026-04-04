from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyPerformance:
    name: str
    replay_alpha_density_lcb: float = 0.0
    shadow_alpha_density_lcb: float = 0.0
    probe_alpha_density_lcb: float = 0.0
    live_alpha_density_lcb: float = 0.0
    operational_penalty: float = 0.0
    broker_mismatch_rate: float = 0.0
    sample_count: int = 0


@dataclass(frozen=True)
class ChampionDecision:
    champion: str
    promoted: bool
    reason: str
    scores: dict[str, float]


def composite_policy_score(perf: PolicyPerformance) -> float:
    weighted = (
        perf.replay_alpha_density_lcb * 0.30
        + perf.shadow_alpha_density_lcb * 0.15
        + perf.probe_alpha_density_lcb * 0.25
        + perf.live_alpha_density_lcb * 0.30
    )
    penalties = perf.operational_penalty + max(0.0, perf.broker_mismatch_rate * 0.50)
    return round(weighted - penalties, 12)


def select_champion_policy(
    *,
    current: PolicyPerformance,
    challengers: list[PolicyPerformance],
    min_sample_count: int = 30,
    min_score_improvement: float = 0.002,
) -> ChampionDecision:
    scores: dict[str, float] = {current.name: composite_policy_score(current)}

    eligible: list[PolicyPerformance] = []
    for challenger in challengers:
        scores[challenger.name] = composite_policy_score(challenger)
        if challenger.sample_count >= min_sample_count:
            eligible.append(challenger)

    if not eligible:
        return ChampionDecision(
            champion=current.name,
            promoted=False,
            reason="no_eligible_challengers",
            scores=scores,
        )

    best = max(eligible, key=lambda row: (scores[row.name], row.sample_count, row.name))
    current_score = scores[current.name]
    best_score = scores[best.name]

    if best_score >= (current_score + float(min_score_improvement)):
        return ChampionDecision(
            champion=best.name,
            promoted=True,
            reason="challenger_outperformed",
            scores=scores,
        )

    return ChampionDecision(
        champion=current.name,
        promoted=False,
        reason="insufficient_improvement",
        scores=scores,
    )
