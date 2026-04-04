from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CounterfactualAttribution:
    actual_pnl: float
    crossed_now_pnl: float
    worked_passive_pnl: float
    skipped_pnl: float
    half_size_pnl: float
    execution_alpha: float
    selection_alpha: float
    sizing_alpha: float


def compute_counterfactual_attribution(
    *,
    actual_pnl: float,
    crossed_now_pnl: float,
    worked_passive_pnl: float,
    skipped_pnl: float = 0.0,
    half_size_pnl: float | None = None,
) -> CounterfactualAttribution:
    """
    Decompose live trade outcome into rough contribution channels:
    - execution_alpha: actual vs immediate-cross baseline
    - selection_alpha: baseline vs skipping the trade
    - sizing_alpha: actual vs half-size run
    """

    if half_size_pnl is None:
        half_size_pnl = actual_pnl * 0.5

    actual = float(actual_pnl)
    crossed = float(crossed_now_pnl)
    worked = float(worked_passive_pnl)
    skipped = float(skipped_pnl)
    half = float(half_size_pnl)

    execution_alpha = actual - crossed
    selection_alpha = crossed - skipped
    sizing_alpha = actual - half

    return CounterfactualAttribution(
        actual_pnl=actual,
        crossed_now_pnl=crossed,
        worked_passive_pnl=worked,
        skipped_pnl=skipped,
        half_size_pnl=half,
        execution_alpha=round(execution_alpha, 6),
        selection_alpha=round(selection_alpha, 6),
        sizing_alpha=round(sizing_alpha, 6),
    )
