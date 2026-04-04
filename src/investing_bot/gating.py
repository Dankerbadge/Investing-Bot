from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True)
class LiquidityGate:
    min_fill_probability: float = 0.55
    max_quote_age_seconds: float = 3.0
    min_book_depth_contracts: int = 20
    max_spread_cost: float = 0.03
    min_confidence: float = 0.55


def evaluate_liquidity(candidate: Candidate, gate: LiquidityGate) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    if candidate.fill_probability < gate.min_fill_probability:
        reasons.append("fill_probability_below_min")
    if candidate.quote_age_seconds > gate.max_quote_age_seconds:
        reasons.append("quote_stale")
    if candidate.book_depth_contracts < gate.min_book_depth_contracts:
        reasons.append("book_depth_too_thin")
    if candidate.spread_cost > gate.max_spread_cost:
        reasons.append("spread_too_wide")
    if candidate.confidence < gate.min_confidence:
        reasons.append("confidence_below_min")

    return (len(reasons) == 0), reasons
