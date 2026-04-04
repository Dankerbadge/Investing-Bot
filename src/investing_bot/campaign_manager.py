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


@dataclass(frozen=True)
class AlphaCampaign:
    alpha_name: str
    stage: str
    allocated_probe_budget: float
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
    multipliers = {
        "disabled": 0.0,
        "shadow": 0.0,
        "probe": 0.05,
        "scaled_1": 0.10,
        "scaled_2": 0.15,
        "scaled_3": 0.25,
        "mature": 0.25,
    }
    stage_mult = multipliers.get(stage_norm, 0.05)
    health = max(0.0, min(1.0, float(bucket_health_score)))
    allocated = max(float(min_budget), float(total_budget) * stage_mult * health)
    return round(max(0.0, allocated), 6)


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
    ) -> AlphaCampaign:
        key = str(alpha_name or "").strip().lower()
        if not key:
            raise ValueError("alpha_name is required")
        stage_norm = _normalize_stage(stage)
        budget = allocate_probe_budget(
            alpha_name=key,
            stage=stage_norm,
            total_budget=total_budget,
            bucket_health_score=bucket_health_score,
        )
        campaign = AlphaCampaign(alpha_name=key, stage=stage_norm, allocated_probe_budget=budget)
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
            spent_budget=campaign.spent_budget,
            confirmed_samples=campaign.confirmed_samples,
            test_state=campaign.test_state,
        )
        self.campaigns[key] = updated
        return updated

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
