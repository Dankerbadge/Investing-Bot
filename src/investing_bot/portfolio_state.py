from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import LedgerEntry, PortfolioLedger


@dataclass(frozen=True)
class PositionState:
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    max_loss: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0


@dataclass(frozen=True)
class PortfolioState:
    cash_balance: float
    net_liquidation_value: float
    gross_exposure: float
    net_exposure: float
    realized_pnl: float
    unrealized_pnl: float
    total_max_loss: float
    positions: tuple[PositionState, ...]


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


def _apply_trade(
    *,
    quantity: float,
    avg_cost: float,
    realized_pnl: float,
    trade_delta: float,
    trade_price: float,
) -> tuple[float, float, float]:
    if trade_delta == 0:
        return quantity, avg_cost, realized_pnl

    if quantity == 0 or (quantity > 0 and trade_delta > 0) or (quantity < 0 and trade_delta < 0):
        new_qty = quantity + trade_delta
        if new_qty == 0:
            return 0.0, 0.0, realized_pnl
        weighted_cost = (abs(quantity) * avg_cost) + (abs(trade_delta) * trade_price)
        return new_qty, weighted_cost / abs(new_qty), realized_pnl

    closing_qty = min(abs(quantity), abs(trade_delta))
    if quantity > 0 and trade_delta < 0:
        realized_pnl += closing_qty * (trade_price - avg_cost)
    elif quantity < 0 and trade_delta > 0:
        realized_pnl += closing_qty * (avg_cost - trade_price)

    new_qty = quantity + trade_delta
    if new_qty == 0:
        return 0.0, 0.0, realized_pnl
    if (quantity > 0 > new_qty) or (quantity < 0 < new_qty):
        return new_qty, trade_price, realized_pnl
    return new_qty, avg_cost, realized_pnl


def compute_portfolio_state(
    *,
    ledger: PortfolioLedger,
    market_quotes: dict[str, float] | None = None,
    greek_snapshots: dict[str, dict[str, float]] | None = None,
    max_loss_by_symbol: dict[str, float] | None = None,
    starting_cash: float = 0.0,
    broker_confirmed_only: bool = True,
) -> PortfolioState:
    quotes = {str(key).upper(): float(value) for key, value in (market_quotes or {}).items()}
    greeks = {str(key).upper(): value for key, value in (greek_snapshots or {}).items()}
    max_loss_map = {str(key).upper(): float(value) for key, value in (max_loss_by_symbol or {}).items()}

    position_qty: dict[str, float] = {}
    position_avg: dict[str, float] = {}
    position_realized: dict[str, float] = {}

    ordered = ledger.ordered_entries(broker_confirmed_only=broker_confirmed_only)
    for entry in ordered:
        _consume_entry(
            entry=entry,
            position_qty=position_qty,
            position_avg=position_avg,
            position_realized=position_realized,
        )

    cash = ledger.cash_balance(starting_cash=starting_cash, broker_confirmed_only=broker_confirmed_only)

    rows: list[PositionState] = []
    realized_total = 0.0
    unrealized_total = 0.0
    gross_exposure = 0.0
    net_exposure = 0.0
    total_max_loss = 0.0

    for symbol in sorted(position_qty):
        qty = position_qty.get(symbol, 0.0)
        if qty == 0.0:
            continue
        avg = position_avg.get(symbol, 0.0)
        price = quotes.get(symbol, avg)
        market_value = qty * price
        unrealized = qty * (price - avg)
        realized = position_realized.get(symbol, 0.0)
        position_max_loss = max_loss_map.get(symbol, abs(qty) * max(0.0, avg))
        greek = greeks.get(symbol, {})

        rows.append(
            PositionState(
                symbol=symbol,
                quantity=round(qty, 6),
                avg_cost=round(avg, 6),
                market_price=round(price, 6),
                market_value=round(market_value, 6),
                unrealized_pnl=round(unrealized, 6),
                realized_pnl=round(realized, 6),
                max_loss=round(position_max_loss, 6),
                delta=round(_as_float(greek.get("delta"), default=0.0), 6),
                gamma=round(_as_float(greek.get("gamma"), default=0.0), 6),
                vega=round(_as_float(greek.get("vega"), default=0.0), 6),
                theta=round(_as_float(greek.get("theta"), default=0.0), 6),
            )
        )

        realized_total += realized
        unrealized_total += unrealized
        gross_exposure += abs(market_value)
        net_exposure += market_value
        total_max_loss += position_max_loss

    net_liq = cash + net_exposure
    return PortfolioState(
        cash_balance=round(cash, 6),
        net_liquidation_value=round(net_liq, 6),
        gross_exposure=round(gross_exposure, 6),
        net_exposure=round(net_exposure, 6),
        realized_pnl=round(realized_total, 6),
        unrealized_pnl=round(unrealized_total, 6),
        total_max_loss=round(total_max_loss, 6),
        positions=tuple(rows),
    )


def _consume_entry(
    *,
    entry: LedgerEntry,
    position_qty: dict[str, float],
    position_avg: dict[str, float],
    position_realized: dict[str, float],
) -> None:
    side = str(entry.side or "").strip().lower()
    symbol = str(entry.symbol or "").strip().upper()
    if side not in {"buy", "sell"} or not symbol:
        return
    quantity = max(0.0, _as_float(entry.quantity, default=0.0))
    if quantity <= 0:
        return
    price = max(0.0, _as_float(entry.price, default=0.0))
    trade_delta = quantity if side == "buy" else -quantity

    current_qty = position_qty.get(symbol, 0.0)
    current_avg = position_avg.get(symbol, 0.0)
    current_realized = position_realized.get(symbol, 0.0)

    new_qty, new_avg, new_realized = _apply_trade(
        quantity=current_qty,
        avg_cost=current_avg,
        realized_pnl=current_realized,
        trade_delta=trade_delta,
        trade_price=price,
    )

    position_qty[symbol] = new_qty
    position_avg[symbol] = new_avg
    position_realized[symbol] = new_realized
