from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .sequential_tests import (
    SequentialTestState,
    lower_confidence_bound,
    should_kill_alpha,
    should_promote_alpha,
    update_state,
)

DEFAULT_ALPHA_PROBE_WEIGHTS: dict[str, float] = {
    "post_event_iv": 0.60,
    "filing_vol": 0.25,
    "open_drive": 0.15,
}

_STAGE_MULTIPLIERS: dict[str, float] = {
    "disabled": 0.0,
    "shadow": 0.0,
    "probe": 0.05,
    "scaled_1": 0.10,
    "scaled_2": 0.15,
    "scaled_3": 0.25,
    "mature": 0.25,
}


@dataclass(frozen=True)
class AlphaCampaign:
    alpha_name: str
    stage: str
    allocated_probe_budget: float
    family_probe_weight: float = 1.0
    spent_budget: float = 0.0
    confirmed_samples: int = 0
    test_state: SequentialTestState = SequentialTestState()


@dataclass(frozen=True)
class CampaignDecision:
    alpha_name: str
    current_stage: str
    next_stage: str
    promote: bool
    kill: bool
    reason: str
    lcb95: float


@dataclass(frozen=True)
class FamilyBudgetEvidence:
    alpha_name: str
    live_alpha_density_lcb: float = 0.0
    capital_efficiency: float = 0.0
    broker_confirmed_live_samples: int = 0


def _normalize_stage(stage: str) -> str:
    text = str(stage or "").strip().lower()
    if text in {"scaled", "scaled_1"}:
        return "scaled_1"
    if text in {"scaled_2", "scaled_3", "mature", "probe", "shadow", "disabled"}:
        return text
    return "probe"


def allocate_probe_budget(
    *,
    alpha_name: str,
    stage: str,
    total_budget: float,
    bucket_health_score: float = 1.0,
    min_budget: float = 0.0,
) -> float:
    stage_norm = _normalize_stage(stage)
    stage_mult = _STAGE_MULTIPLIERS.get(stage_norm, 0.05)
    health = max(0.0, min(1.0, float(bucket_health_score)))
    allocated = max(float(min_budget), float(total_budget) * stage_mult * health)
    return round(max(0.0, allocated), 6)


def resolve_family_probe_weight(
    alpha_name: str,
    *,
    family_probe_weights: dict[str, float] | None = None,
    default_weight: float = 0.10,
) -> float:
    key = str(alpha_name or "").strip().lower()
    if not key:
        return max(0.0, float(default_weight))

    merged = dict(DEFAULT_ALPHA_PROBE_WEIGHTS)
    if family_probe_weights:
        for name, weight in family_probe_weights.items():
            name_key = str(name or "").strip().lower()
            if not name_key:
                continue
            value = max(0.0, float(weight))
            if value > 0:
                merged[name_key] = value
            elif name_key in merged:
                merged.pop(name_key, None)

    value = merged.get(key)
    if value is None:
        value = max(0.0, float(default_weight))
    return round(float(value), 6)


def derive_adaptive_family_weights(
    *,
    alpha_names: list[str] | tuple[str, ...],
    evidence_by_alpha: dict[str, FamilyBudgetEvidence | dict[str, Any]] | None = None,
    baseline_weights: dict[str, float] | None = None,
    min_floor_weight: float = 0.10,
    max_cap_weight: float = 0.70,
    min_live_samples_for_scale: int = 30,
    default_weight: float = 0.10,
) -> dict[str, float]:
    keys = [str(name or "").strip().lower() for name in alpha_names if str(name or "").strip()]
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}

    n = len(keys)
    floor = min(max(0.0, float(min_floor_weight)), 1.0 / n)
    cap = max(floor, min(1.0, float(max_cap_weight)))

    evidence_map: dict[str, FamilyBudgetEvidence] = {}
    for key, row in (evidence_by_alpha or {}).items():
        name = str(key or "").strip().lower()
        if not name:
            continue
        if isinstance(row, FamilyBudgetEvidence):
            evidence_map[name] = row
            continue
        if isinstance(row, dict):
            evidence_map[name] = FamilyBudgetEvidence(
                alpha_name=name,
                live_alpha_density_lcb=float(row.get("live_alpha_density_lcb") or 0.0),
                capital_efficiency=float(row.get("capital_efficiency") or 0.0),
                broker_confirmed_live_samples=int(row.get("broker_confirmed_live_samples") or 0),
            )

    raw_scores: dict[str, float] = {}
    for key in keys:
        baseline = resolve_family_probe_weight(
            key,
            family_probe_weights=baseline_weights,
            default_weight=default_weight,
        )
        evidence = evidence_map.get(key)
        if evidence is None:
            raw_scores[key] = max(0.0, baseline)
            continue

        confidence = min(1.0, max(0.0, evidence.broker_confirmed_live_samples / max(1, int(min_live_samples_for_scale))))
        edge_signal = max(-1.0, min(1.5, evidence.live_alpha_density_lcb / 0.02))
        efficiency_signal = max(-1.0, min(1.5, evidence.capital_efficiency / 0.02))
        adjustment = 1.0 + confidence * ((edge_signal * 0.60) + (efficiency_signal * 0.40))
        raw_scores[key] = max(0.000001, baseline * max(0.1, adjustment))

    weights = {key: floor for key in keys}
    remaining = max(0.0, 1.0 - (floor * n))
    if remaining <= 0:
        return weights

    capacity = {key: max(0.0, cap - floor) for key in keys}
    free = {key for key in keys if capacity[key] > 0}
    eps = 1e-12
    while remaining > eps and free:
        raw_total = sum(max(eps, raw_scores[key]) for key in free)
        if raw_total <= eps:
            equal_share = remaining / len(free)
            for key in list(free):
                delta = min(capacity[key], equal_share)
                weights[key] += delta
                capacity[key] -= delta
                remaining -= delta
                if capacity[key] <= eps:
                    free.remove(key)
            continue

        tentative = {key: remaining * (max(eps, raw_scores[key]) / raw_total) for key in free}
        capped = [key for key in free if tentative[key] >= (capacity[key] - eps)]
        if not capped:
            for key in free:
                delta = min(capacity[key], tentative[key])
                weights[key] += delta
                capacity[key] -= delta
                remaining -= delta
            break

        for key in capped:
            delta = capacity[key]
            weights[key] += delta
            remaining -= delta
            capacity[key] = 0.0
            free.remove(key)

    # Numerical cleanup to keep sum exactly 1 while respecting bounds.
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        diff = 1.0 - total
        ordered = sorted(keys, key=lambda key: raw_scores.get(key, 0.0), reverse=True)
        for key in ordered:
            candidate = weights[key] + diff
            if floor - 1e-9 <= candidate <= cap + 1e-9:
                weights[key] = candidate
                break

    return {key: float(weights[key]) for key in keys}


@dataclass
class CampaignManager:
    campaigns: dict[str, AlphaCampaign] = field(default_factory=dict)

    def start_campaign(
        self,
        *,
        alpha_name: str,
        stage: str,
        total_budget: float,
        bucket_health_score: float = 1.0,
        family_probe_weights: dict[str, float] | None = None,
        default_family_probe_weight: float = 0.10,
    ) -> AlphaCampaign:
        key = str(alpha_name or "").strip().lower()
        if not key:
            raise ValueError("alpha_name is required")
        stage_norm = _normalize_stage(stage)
        family_weight = resolve_family_probe_weight(
            key,
            family_probe_weights=family_probe_weights,
            default_weight=default_family_probe_weight,
        )
        budget = allocate_probe_budget(
            alpha_name=key,
            stage=stage_norm,
            total_budget=total_budget,
            bucket_health_score=bucket_health_score,
        )
        campaign = AlphaCampaign(
            alpha_name=key,
            stage=stage_norm,
            allocated_probe_budget=budget,
            family_probe_weight=family_weight,
        )
        self.campaigns[key] = campaign
        return campaign

    def get_campaign(self, alpha_name: str) -> AlphaCampaign | None:
        key = str(alpha_name or "").strip().lower()
        if not key:
            return None
        return self.campaigns.get(key)

    def update_alpha_posterior(
        self,
        *,
        alpha_name: str,
        realized_alpha_density: float,
        probe_cost: float = 0.0,
        broker_confirmed: bool = True,
    ) -> AlphaCampaign:
        key = str(alpha_name or "").strip().lower()
        campaign = self.campaigns.get(key)
        if campaign is None:
            raise KeyError(f"campaign not found: {alpha_name}")

        state = campaign.test_state
        confirmed_samples = campaign.confirmed_samples
        if broker_confirmed:
            state = update_state(state, float(realized_alpha_density))
            confirmed_samples += 1

        updated = AlphaCampaign(
            alpha_name=campaign.alpha_name,
            stage=campaign.stage,
            allocated_probe_budget=campaign.allocated_probe_budget,
            family_probe_weight=campaign.family_probe_weight,
            spent_budget=round(campaign.spent_budget + max(0.0, float(probe_cost)), 6),
            confirmed_samples=confirmed_samples,
            test_state=state,
        )
        self.campaigns[key] = updated
        return updated

    def allocate_probe_budget(
        self,
        *,
        alpha_name: str,
        total_budget: float,
        bucket_health_score: float = 1.0,
    ) -> AlphaCampaign:
        key = str(alpha_name or "").strip().lower()
        campaign = self.campaigns.get(key)
        if campaign is None:
            raise KeyError(f"campaign not found: {alpha_name}")

        allocated = allocate_probe_budget(
            alpha_name=campaign.alpha_name,
            stage=campaign.stage,
            total_budget=total_budget,
            bucket_health_score=bucket_health_score,
        )
        updated = AlphaCampaign(
            alpha_name=campaign.alpha_name,
            stage=campaign.stage,
            allocated_probe_budget=allocated,
            family_probe_weight=campaign.family_probe_weight,
            spent_budget=campaign.spent_budget,
            confirmed_samples=campaign.confirmed_samples,
            test_state=campaign.test_state,
        )
        self.campaigns[key] = updated
        return updated

    def allocate_family_probe_budgets(
        self,
        *,
        total_budget: float,
        bucket_health_by_alpha: dict[str, float] | None = None,
        family_probe_weights: dict[str, float] | None = None,
        default_family_probe_weight: float = 0.10,
        adaptive_evidence_by_alpha: dict[str, FamilyBudgetEvidence | dict[str, Any]] | None = None,
        min_floor_weight: float = 0.10,
        max_cap_weight: float = 0.70,
        min_live_samples_for_scale: int = 30,
    ) -> dict[str, AlphaCampaign]:
        if not self.campaigns:
            return {}

        health_map = {str(key).strip().lower(): float(value) for key, value in (bucket_health_by_alpha or {}).items()}
        active_names = list(self.campaigns.keys())
        adaptive_weights = derive_adaptive_family_weights(
            alpha_names=active_names,
            evidence_by_alpha=adaptive_evidence_by_alpha,
            baseline_weights=family_probe_weights,
            min_floor_weight=min_floor_weight,
            max_cap_weight=max_cap_weight,
            min_live_samples_for_scale=min_live_samples_for_scale,
            default_weight=default_family_probe_weight,
        )
        rows: list[tuple[str, AlphaCampaign, float, float]] = []
        for alpha_name, campaign in self.campaigns.items():
            stage_mult = _STAGE_MULTIPLIERS.get(_normalize_stage(campaign.stage), 0.05)
            health = max(0.0, min(1.0, health_map.get(alpha_name, 1.0)))
            family_weight = adaptive_weights.get(alpha_name, campaign.family_probe_weight)
            weighted_score = stage_mult * health * family_weight
            rows.append((alpha_name, campaign, weighted_score, family_weight))

        denominator = sum(score for _, _, score, _ in rows if score > 0)
        updated_campaigns: dict[str, AlphaCampaign] = {}
        for alpha_name, campaign, score, family_weight in rows:
            allocated = 0.0
            if denominator > 0 and score > 0:
                allocated = float(total_budget) * (score / denominator)
            updated = AlphaCampaign(
                alpha_name=campaign.alpha_name,
                stage=campaign.stage,
                allocated_probe_budget=round(max(0.0, allocated), 6),
                family_probe_weight=round(max(0.0, family_weight), 6),
                spent_budget=campaign.spent_budget,
                confirmed_samples=campaign.confirmed_samples,
                test_state=campaign.test_state,
            )
            self.campaigns[alpha_name] = updated
            updated_campaigns[alpha_name] = updated
        return updated_campaigns

    def should_promote_alpha(
        self,
        *,
        alpha_name: str,
        min_samples: int = 30,
        min_lcb: float = 0.0,
        min_success_rate: float = 0.50,
    ) -> bool:
        campaign = self.get_campaign(alpha_name)
        if campaign is None:
            return False
        return should_promote_alpha(
            state=campaign.test_state,
            min_samples=min_samples,
            min_lcb=min_lcb,
            min_success_rate=min_success_rate,
        )

    def should_kill_alpha(
        self,
        *,
        alpha_name: str,
        min_samples: int = 30,
        max_ucb: float = 0.0,
    ) -> bool:
        campaign = self.get_campaign(alpha_name)
        if campaign is None:
            return False
        return should_kill_alpha(state=campaign.test_state, min_samples=min_samples, max_ucb=max_ucb)

    def evaluate_alpha(
        self,
        *,
        alpha_name: str,
        min_samples: int = 30,
        min_lcb: float = 0.0,
        max_ucb_kill: float = -0.001,
    ) -> CampaignDecision:
        campaign = self.get_campaign(alpha_name)
        if campaign is None:
            raise KeyError(f"campaign not found: {alpha_name}")

        lcb = lower_confidence_bound(campaign.test_state)
        promote = self.should_promote_alpha(alpha_name=alpha_name, min_samples=min_samples, min_lcb=min_lcb)
        kill = self.should_kill_alpha(alpha_name=alpha_name, min_samples=min_samples, max_ucb=max_ucb_kill)

        stage_order = ["disabled", "shadow", "probe", "scaled_1", "scaled_2", "scaled_3", "mature"]
        current = _normalize_stage(campaign.stage)
        idx = stage_order.index(current) if current in stage_order else 2
        next_stage = current
        reason = "hold"

        if kill:
            next_stage = "disabled"
            reason = "kill_alpha"
        elif promote and idx < (len(stage_order) - 1):
            next_stage = stage_order[idx + 1]
            reason = "promote_alpha"

        updated = AlphaCampaign(
            alpha_name=campaign.alpha_name,
            stage=next_stage,
            allocated_probe_budget=campaign.allocated_probe_budget,
            family_probe_weight=campaign.family_probe_weight,
            spent_budget=campaign.spent_budget,
            confirmed_samples=campaign.confirmed_samples,
            test_state=campaign.test_state,
        )
        self.campaigns[campaign.alpha_name] = updated

        return CampaignDecision(
            alpha_name=campaign.alpha_name,
            current_stage=current,
            next_stage=next_stage,
            promote=promote and not kill,
            kill=kill,
            reason=reason,
            lcb95=round(lcb, 12),
        )
