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


def _is_defined_risk(structure_type: str) -> bool:
    text = str(structure_type or "").strip().lower()
    if not text:
        return True
    if "naked" in text:
        return False
    if "undefined" in text:
        return False
    return True


@dataclass(frozen=True)
class StructureCandidate:
    structure_id: str
    structure_type: str
    alpha_density_lcb: float
    spread_cost: float
    assignment_risk: float
    capital_required: float
    max_loss: float
    expected_hold_minutes: float = 60.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StructureDecision:
    selected: StructureCandidate | None
    ranked: tuple[StructureCandidate, ...]
    rejected: tuple[StructureCandidate, ...]
    reason: str


def structure_score(
    candidate: StructureCandidate,
    *,
    assignment_penalty_weight: float = 0.40,
    spread_penalty_weight: float = 1.0,
    capital_penalty_weight: float = 0.15,
) -> float:
    capital = max(1.0, candidate.capital_required)
    max_loss_ratio = max(0.0, candidate.max_loss / capital)
    score = (
        candidate.alpha_density_lcb
        - (candidate.spread_cost * spread_penalty_weight)
        - (candidate.assignment_risk * assignment_penalty_weight)
        - (max(0.0, max_loss_ratio - 1.0) * capital_penalty_weight)
    )
    return round(score, 12)


def select_structure(
    structures: list[StructureCandidate],
    *,
    max_assignment_risk: float = 0.60,
    max_capital_required: float | None = None,
    require_defined_risk: bool = True,
) -> StructureDecision:
    if not structures:
        return StructureDecision(selected=None, ranked=(), rejected=(), reason="no_structures")

    ranked = sorted(
        structures,
        key=lambda row: (structure_score(row), row.alpha_density_lcb, -row.spread_cost, row.structure_id),
        reverse=True,
    )

    rejected: list[StructureCandidate] = []
    eligible: list[StructureCandidate] = []
    capital_cap = None if max_capital_required is None else max(0.0, float(max_capital_required))

    for row in ranked:
        if require_defined_risk and not _is_defined_risk(row.structure_type):
            rejected.append(row)
            continue
        if row.assignment_risk > float(max_assignment_risk):
            rejected.append(row)
            continue
        if capital_cap is not None and row.capital_required > capital_cap:
            rejected.append(row)
            continue
        eligible.append(row)

    if not eligible:
        return StructureDecision(
            selected=None,
            ranked=tuple(ranked),
            rejected=tuple(rejected),
            reason="no_eligible_structures",
        )

    return StructureDecision(
        selected=eligible[0],
        ranked=tuple(ranked),
        rejected=tuple(rejected),
        reason="selected_best_lcb_structure",
    )
