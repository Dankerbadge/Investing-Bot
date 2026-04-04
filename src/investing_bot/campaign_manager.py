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
    ) -> dict[str, AlphaCampaign]:
        if not self.campaigns:
            return {}

        health_map = {str(key).strip().lower(): float(value) for key, value in (bucket_health_by_alpha or {}).items()}
        rows: list[tuple[str, AlphaCampaign, float]] = []
        for alpha_name, campaign in self.campaigns.items():
            stage_mult = _STAGE_MULTIPLIERS.get(_normalize_stage(campaign.stage), 0.05)
            health = max(0.0, min(1.0, health_map.get(alpha_name, 1.0)))
            family_weight = resolve_family_probe_weight(
                alpha_name,
                family_probe_weights=family_probe_weights,
                default_weight=default_family_probe_weight,
            )
            weighted_score = stage_mult * health * family_weight
            rows.append((alpha_name, campaign, weighted_score))

        denominator = sum(score for _, _, score in rows if score > 0)
        updated_campaigns: dict[str, AlphaCampaign] = {}
        for alpha_name, campaign, score in rows:
            allocated = 0.0
            if denominator > 0 and score > 0:
                allocated = float(total_budget) * (score / denominator)
            updated = AlphaCampaign(
                alpha_name=campaign.alpha_name,
                stage=campaign.stage,
                allocated_probe_budget=round(max(0.0, allocated), 6),
                family_probe_weight=resolve_family_probe_weight(
                    alpha_name,
                    family_probe_weights=family_probe_weights,
                    default_weight=default_family_probe_weight,
                ),
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
