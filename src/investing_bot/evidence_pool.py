from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class EvidenceRecord:
    alpha_family: str
    evidence_universe: str
    metric: float
    sample_count: int


@dataclass(frozen=True)
class PooledEstimate:
    alpha_family: str
    evidence_universe: str
    lane: str
    local_metric: float
    local_samples: int
    universe_mean: float
    family_mean: float
    global_mean: float
    pooled_metric: float


@dataclass
class EvidencePool:
    records: list[EvidenceRecord] = field(default_factory=list)

    def add(
        self,
        *,
        alpha_family: str,
        evidence_universe: str,
        metric: float,
        sample_count: int,
    ) -> None:
        family = _normalize(alpha_family)
        universe = _normalize(evidence_universe)
        if not family or not universe:
            return
        self.records.append(
            EvidenceRecord(
                alpha_family=family,
                evidence_universe=universe,
                metric=float(metric),
                sample_count=max(0, int(sample_count)),
            )
        )

    def _weighted_mean(self, rows: list[EvidenceRecord]) -> float:
        weighted_total = 0.0
        weight_sum = 0.0
        for row in rows:
            weight = max(1.0, float(row.sample_count))
            weighted_total += row.metric * weight
            weight_sum += weight
        if weight_sum <= 0:
            return 0.0
        return weighted_total / weight_sum

    def _means(self, alpha_family: str, evidence_universe: str) -> tuple[float, float, float]:
        family = _normalize(alpha_family)
        universe = _normalize(evidence_universe)

        global_mean = self._weighted_mean(self.records)
        family_rows = [row for row in self.records if row.alpha_family == family]
        family_mean = self._weighted_mean(family_rows) if family_rows else global_mean

        universe_rows = [
            row
            for row in family_rows
            if row.evidence_universe == universe
        ]
        universe_mean = self._weighted_mean(universe_rows) if universe_rows else family_mean
        return universe_mean, family_mean, global_mean

    def estimate(
        self,
        *,
        alpha_family: str,
        evidence_universe: str,
        local_metric: float,
        local_samples: int,
        lane: str = "shadow",
        local_weight_per_sample: float = 1.0,
        universe_prior_weight: float = 20.0,
        family_prior_weight: float = 10.0,
        global_prior_weight: float = 5.0,
    ) -> PooledEstimate:
        family = _normalize(alpha_family)
        universe = _normalize(evidence_universe)
        lane_norm = _normalize(lane) or "shadow"

        local = float(local_metric)
        samples = max(0, int(local_samples))
        universe_mean, family_mean, global_mean = self._means(family, universe)

        local_weight = max(0.0, samples * float(local_weight_per_sample))
        pooled = (
            (local * local_weight)
            + (universe_mean * max(0.0, float(universe_prior_weight)))
            + (family_mean * max(0.0, float(family_prior_weight)))
            + (global_mean * max(0.0, float(global_prior_weight)))
        )
        denom = local_weight + max(0.0, float(universe_prior_weight)) + max(0.0, float(family_prior_weight)) + max(0.0, float(global_prior_weight))
        pooled_metric = (pooled / denom) if denom > 0 else local

        # Capital lane must never be boosted above local broker-confirmed evidence.
        if lane_norm == "capital":
            if samples <= 0:
                pooled_metric = 0.0
            else:
                pooled_metric = min(local, pooled_metric)

        return PooledEstimate(
            alpha_family=family,
            evidence_universe=universe,
            lane=lane_norm,
            local_metric=round(local, 12),
            local_samples=samples,
            universe_mean=round(universe_mean, 12),
            family_mean=round(family_mean, 12),
            global_mean=round(global_mean, 12),
            pooled_metric=round(pooled_metric, 12),
        )



def build_evidence_pool(rows: list[dict[str, Any]]) -> EvidencePool:
    pool = EvidencePool()
    for row in rows:
        if not isinstance(row, dict):
            continue
        family = row.get("alpha_family") or row.get("family")
        universe = row.get("evidence_universe") or row.get("universe")
        metric = _as_float(row.get("metric") or row.get("live_alpha_density_lcb") or row.get("alpha_density_lcb"), 0.0)
        samples = int(_as_float(row.get("sample_count") or row.get("broker_confirmed_live_samples"), 0.0))
        pool.add(alpha_family=str(family), evidence_universe=str(universe), metric=metric, sample_count=samples)
    return pool



def capped_live_metric(local_metric: float, pooled_metric: float) -> float:
    return min(float(local_metric), float(pooled_metric))
