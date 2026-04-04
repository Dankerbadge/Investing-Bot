from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyPerformance:
    name: str
    alpha_family: str = ""
    execution_style: str = ""
    evidence_universe: str = ""
    replay_alpha_density_lcb: float = 0.0
    shadow_alpha_density_lcb: float = 0.0
    probe_alpha_density_lcb: float = 0.0
    live_alpha_density_lcb: float = 0.0
    broker_confirmed_live_samples: int = 0
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


def _normalize_scope(value: str) -> str:
    return str(value or "").strip().lower()


def _scope_matches(current: PolicyPerformance, challenger: PolicyPerformance) -> bool:
    if _normalize_scope(current.alpha_family):
        if _normalize_scope(challenger.alpha_family) != _normalize_scope(current.alpha_family):
            return False
    if _normalize_scope(current.execution_style):
        if _normalize_scope(challenger.execution_style) != _normalize_scope(current.execution_style):
            return False
    if _normalize_scope(current.evidence_universe):
        if _normalize_scope(challenger.evidence_universe) != _normalize_scope(current.evidence_universe):
            return False
    return True


def select_champion_policy(
    *,
    current: PolicyPerformance,
    challengers: list[PolicyPerformance],
    min_sample_count: int = 30,
    min_broker_confirmed_live_samples: int = 30,
    min_live_alpha_density_lcb: float = 0.0,
    min_score_improvement: float = 0.002,
    require_local_scope_match: bool = True,
) -> ChampionDecision:
    scores: dict[str, float] = {current.name: composite_policy_score(current)}

    eligible: list[PolicyPerformance] = []
    scope_filtered_count = 0
    for challenger in challengers:
        scores[challenger.name] = composite_policy_score(challenger)
        if require_local_scope_match and not _scope_matches(current, challenger):
            scope_filtered_count += 1
            continue
        if challenger.sample_count < min_sample_count:
            continue
        if challenger.broker_confirmed_live_samples < min_broker_confirmed_live_samples:
            continue
        if challenger.live_alpha_density_lcb <= float(min_live_alpha_density_lcb):
            continue
        eligible.append(challenger)

    if not eligible:
        reason = "no_eligible_challengers"
        if scope_filtered_count > 0 and scope_filtered_count == len(challengers):
            reason = "no_scope_matched_challengers"
        return ChampionDecision(
            champion=current.name,
            promoted=False,
            reason=reason,
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
