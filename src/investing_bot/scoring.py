from __future__ import annotations

from dataclasses import dataclass

from .models import Candidate


@dataclass(frozen=True)
class ExecutionAdjustments:
    expected_fill_probability: float | None = None
    slippage_p95_penalty: float = 0.0
    post_fill_alpha_decay_penalty: float = 0.0
    uncertainty_penalty: float = 0.0
    execution_penalty: float = 0.0
    model_error_score: float = 0.0


@dataclass(frozen=True)
class EdgeBreakdown:
    raw_net_edge: float
    adjusted_net_edge: float
    expected_fill_probability: float
    slippage_p95_penalty: float
    post_fill_alpha_decay_penalty: float
    uncertainty_penalty: float
    execution_penalty: float
    model_error_score: float


def compute_edge_breakdown(candidate: Candidate, adjustments: ExecutionAdjustments | None = None) -> EdgeBreakdown:
    """
    Execution-aware score with optional realized-edge learning adjustments.

    raw_net_edge =
        (surface_residual * convergence_probability * fill_probability)
        - spread_cost
        - hedge_cost
        - stale_quote_penalty
        - event_gap_penalty
        - capital_lockup_penalty

    adjusted_net_edge = raw_net_edge
        - slippage_p95_penalty
        - post_fill_alpha_decay_penalty
        - uncertainty_penalty
        - execution_penalty
    """

    adj = adjustments or ExecutionAdjustments()
    fill_probability = float(candidate.fill_probability)
    if isinstance(adj.expected_fill_probability, float):
        fill_probability = min(1.0, max(0.0, float(adj.expected_fill_probability)))

    gross = (
        float(candidate.surface_residual)
        * float(candidate.convergence_probability)
        * fill_probability
    )
    costs = (
        float(candidate.spread_cost)
        + float(candidate.hedge_cost)
        + float(candidate.stale_quote_penalty)
        + float(candidate.event_gap_penalty)
        + float(candidate.capital_lockup_penalty)
    )
    raw = gross - costs

    slippage_pen = max(0.0, float(adj.slippage_p95_penalty))
    alpha_decay_pen = max(0.0, float(adj.post_fill_alpha_decay_penalty))
    uncertainty_pen = max(0.0, float(adj.uncertainty_penalty))
    execution_pen = max(0.0, float(adj.execution_penalty))

    adjusted = raw - slippage_pen - alpha_decay_pen - uncertainty_pen - execution_pen

    return EdgeBreakdown(
        raw_net_edge=raw,
        adjusted_net_edge=adjusted,
        expected_fill_probability=fill_probability,
        slippage_p95_penalty=slippage_pen,
        post_fill_alpha_decay_penalty=alpha_decay_pen,
        uncertainty_penalty=uncertainty_pen,
        execution_penalty=execution_pen,
        model_error_score=max(0.0, float(adj.model_error_score)),
    )


def compute_net_executable_edge(candidate: Candidate, adjustments: ExecutionAdjustments | None = None) -> float:
    """Backward-compatible net edge API; returns adjusted edge when adjustments are provided."""

    return compute_edge_breakdown(candidate, adjustments).adjusted_net_edge
