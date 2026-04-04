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
    reject_locked_or_crossed_quotes: bool = True
    allow_adjusted_options: bool = False
    allow_nonstandard_expirations: bool = False


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
    if gate.reject_locked_or_crossed_quotes and bool(candidate.metadata.get("quote_locked_or_crossed")):
        reasons.append("locked_or_crossed_market")
    if not gate.allow_adjusted_options and bool(candidate.metadata.get("is_adjusted_option")):
        reasons.append("adjusted_option_excluded")
    if not gate.allow_nonstandard_expirations and bool(candidate.metadata.get("is_nonstandard_expiration")):
        reasons.append("nonstandard_expiration_excluded")

    return (len(reasons) == 0), reasons
