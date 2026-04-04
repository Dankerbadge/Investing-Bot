from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapitalEfficiency:
    expected_net_pnl: float
    capital_minutes: float
    incremental_max_loss: float
    incremental_shock_loss: float
    alpha_density: float
    pnl_per_max_loss: float
    pnl_per_shock_loss: float


def _safe_div(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def compute_capital_efficiency(
    *,
    expected_net_pnl: float,
    notional: float,
    expected_holding_minutes: float,
    incremental_max_loss: float,
    incremental_shock_loss: float,
) -> CapitalEfficiency:
    pnl = float(expected_net_pnl)
    capital_minutes = max(1.0, abs(float(notional)) * max(1.0, float(expected_holding_minutes)))
    max_loss = max(0.0, float(incremental_max_loss))
    shock_loss = max(0.0, float(incremental_shock_loss))

    return CapitalEfficiency(
        expected_net_pnl=round(pnl, 10),
        capital_minutes=round(capital_minutes, 6),
        incremental_max_loss=round(max_loss, 6),
        incremental_shock_loss=round(shock_loss, 6),
        alpha_density=round(_safe_div(pnl, capital_minutes), 12),
        pnl_per_max_loss=round(_safe_div(pnl, max_loss), 12),
        pnl_per_shock_loss=round(_safe_div(pnl, shock_loss), 12),
    )


def rank_by_capital_efficiency(rows: list[tuple[str, CapitalEfficiency]]) -> list[tuple[str, CapitalEfficiency]]:
    return sorted(
        rows,
        key=lambda item: (
            item[1].alpha_density,
            item[1].pnl_per_max_loss,
            item[1].pnl_per_shock_loss,
            item[1].expected_net_pnl,
        ),
        reverse=True,
    )
