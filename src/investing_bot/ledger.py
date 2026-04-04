from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class LedgerEntry:
    entry_id: str
    timestamp: str
    symbol: str
    side: str
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    cash_delta: float | None = None
    broker_confirmed: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


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


def _sort_key(entry: LedgerEntry) -> tuple[int, str, str]:
    text = str(entry.timestamp or "").strip()
    if not text:
        return (1, "", entry.entry_id)
    try:
        iso = datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        return (0, iso, entry.entry_id)
    except ValueError:
        return (1, text, entry.entry_id)


@dataclass
class PortfolioLedger:
    entries: list[LedgerEntry] = field(default_factory=list)

    def add_entry(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)

    def ordered_entries(self, *, broker_confirmed_only: bool = True) -> list[LedgerEntry]:
        rows = self.entries
        if broker_confirmed_only:
            rows = [entry for entry in rows if entry.broker_confirmed]
        return sorted(rows, key=_sort_key)

    def positions(self, *, broker_confirmed_only: bool = True) -> dict[str, float]:
        quantities: dict[str, float] = {}
        for entry in self.ordered_entries(broker_confirmed_only=broker_confirmed_only):
            side = str(entry.side or "").strip().lower()
            symbol = str(entry.symbol or "").strip().upper()
            qty = _as_float(entry.quantity, default=0.0)
            if not symbol or qty <= 0:
                continue
            if side == "buy":
                quantities[symbol] = quantities.get(symbol, 0.0) + qty
            elif side == "sell":
                quantities[symbol] = quantities.get(symbol, 0.0) - qty
        return quantities

    def cash_balance(self, *, starting_cash: float = 0.0, broker_confirmed_only: bool = True) -> float:
        cash = float(starting_cash)
        for entry in self.ordered_entries(broker_confirmed_only=broker_confirmed_only):
            if entry.cash_delta is not None:
                cash += _as_float(entry.cash_delta, default=0.0)
                continue
            side = str(entry.side or "").strip().lower()
            qty = _as_float(entry.quantity, default=0.0)
            price = _as_float(entry.price, default=0.0)
            fee = max(0.0, _as_float(entry.fee, default=0.0))
            notional = qty * price
            if side == "buy":
                cash -= (notional + fee)
            elif side == "sell":
                cash += (notional - fee)
            elif side in {"fee", "commission"}:
                cash -= fee if fee > 0 else abs(notional)
        return round(cash, 6)

    @classmethod
    def from_event_rows(cls, rows: list[dict[str, Any]]) -> PortfolioLedger:
        ledger = cls()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            side = str(row.get("side") or row.get("instruction") or row.get("event_type") or "").strip().lower()
            symbol = str(row.get("symbol") or row.get("ticker") or row.get("underlying") or "").strip().upper()
            entry = LedgerEntry(
                entry_id=str(row.get("entry_id") or row.get("id") or row.get("order_id") or f"evt-{index}"),
                timestamp=str(
                    row.get("timestamp")
                    or row.get("event_time")
                    or row.get("recorded_at")
                    or row.get("updated_at")
                    or ""
                ),
                symbol=symbol,
                side=side,
                quantity=_as_float(row.get("quantity") or row.get("fill_quantity") or row.get("filled_quantity"), default=0.0),
                price=_as_float(row.get("price") or row.get("fill_price") or row.get("average_price"), default=0.0),
                fee=_as_float(row.get("fee") or row.get("commission"), default=0.0),
                cash_delta=(
                    None
                    if row.get("cash_delta") is None
                    else _as_float(row.get("cash_delta"), default=0.0)
                ),
                broker_confirmed=bool(row.get("broker_confirmed", True)),
                metadata={
                    key: value
                    for key, value in row.items()
                    if key
                    not in {
                        "entry_id",
                        "id",
                        "order_id",
                        "timestamp",
                        "event_time",
                        "recorded_at",
                        "updated_at",
                        "symbol",
                        "ticker",
                        "underlying",
                        "side",
                        "instruction",
                        "event_type",
                        "quantity",
                        "fill_quantity",
                        "filled_quantity",
                        "price",
                        "fill_price",
                        "average_price",
                        "fee",
                        "commission",
                        "cash_delta",
                        "broker_confirmed",
                    }
                },
            )
            ledger.add_entry(entry)
        return ledger
