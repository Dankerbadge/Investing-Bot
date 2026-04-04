from __future__ import annotations

from .models import Candidate


def compute_net_executable_edge(candidate: Candidate) -> float:
    """
    Core execution-aware score from the audit:

    net_edge =
        (surface_residual * convergence_probability * fill_probability)
        - spread_cost
        - hedge_cost
        - stale_quote_penalty
        - event_gap_penalty
        - capital_lockup_penalty
    """

    gross = (
        float(candidate.surface_residual)
        * float(candidate.convergence_probability)
        * float(candidate.fill_probability)
    )
    costs = (
        float(candidate.spread_cost)
        + float(candidate.hedge_cost)
        + float(candidate.stale_quote_penalty)
        + float(candidate.event_gap_penalty)
        + float(candidate.capital_lockup_penalty)
    )
    return gross - costs
