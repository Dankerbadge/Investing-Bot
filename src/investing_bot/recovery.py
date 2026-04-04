from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ledger import PortfolioLedger
from .portfolio_state import PortfolioState, compute_portfolio_state
from .reconciliation import BrokerTruthSnapshot, reconcile_order_lifecycle


@dataclass(frozen=True)
class RecoveryState:
    portfolio_state: PortfolioState
    broker_truth_snapshot: BrokerTruthSnapshot
    broker_position_mismatches: tuple[str, ...]
    orphaned_broker_orders: tuple[str, ...]
    stale_local_orders: tuple[str, ...]
    broker_cash_balance: float | None
    cash_balance_difference: float
    parity_ok: bool
    reasons: tuple[str, ...]


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


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _order_id(row: Any) -> str:
    if isinstance(row, str):
        return str(row).strip()
    if not isinstance(row, dict):
        return ""
    for key in ("order_id", "id", "client_order_id", "clientOrderId"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _position_map(rows: list[dict[str, Any]] | None) -> dict[str, float]:
    result: dict[str, float] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        symbol = _normalize_symbol(row.get("symbol") or row.get("ticker") or row.get("underlying"))
        if not symbol:
            continue
        quantity = _as_float(
            row.get("quantity")
            or row.get("position")
            or row.get("net_quantity")
            or row.get("longQuantity"),
            default=0.0,
        )
        result[symbol] = result.get(symbol, 0.0) + quantity
    return result


def detect_orphaned_orders(
    *,
    broker_open_orders: list[dict[str, Any]] | list[str] | None,
    local_open_orders: list[dict[str, Any]] | list[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    broker_ids = {_order_id(row) for row in (broker_open_orders or []) if _order_id(row)}
    local_ids = {_order_id(row) for row in (local_open_orders or []) if _order_id(row)}

    orphaned_broker = tuple(sorted(broker_ids - local_ids))
    stale_local = tuple(sorted(local_ids - broker_ids))
    return orphaned_broker, stale_local


def _extract_broker_cash_balance(balances: dict[str, Any] | None) -> float | None:
    row = balances if isinstance(balances, dict) else {}
    for key in ("cash_balance", "cash", "cashAvailableForTrading", "available_funds"):
        if key in row:
            return _as_float(row.get(key), default=0.0)
    return None


def rebuild_portfolio_truth(
    *,
    ledger: PortfolioLedger,
    balances: dict[str, Any] | None = None,
    market_quotes: dict[str, float] | None = None,
    greek_snapshots: dict[str, dict[str, float]] | None = None,
    max_loss_by_symbol: dict[str, float] | None = None,
    starting_cash: float = 0.0,
    broker_confirmed_only: bool = True,
) -> PortfolioState:
    return compute_portfolio_state(
        ledger=ledger,
        market_quotes=market_quotes,
        greek_snapshots=greek_snapshots,
        max_loss_by_symbol=max_loss_by_symbol,
        starting_cash=float(starting_cash),
        broker_confirmed_only=broker_confirmed_only,
    )


def recover_account_state(
    *,
    ledger: PortfolioLedger,
    balances: dict[str, Any] | None = None,
    positions: list[dict[str, Any]] | None = None,
    open_orders: list[dict[str, Any]] | None = None,
    local_open_orders: list[dict[str, Any]] | list[str] | None = None,
    account_activity_events: list[dict[str, Any]] | None = None,
    market_quotes: dict[str, float] | None = None,
    greek_snapshots: dict[str, dict[str, float]] | None = None,
    max_loss_by_symbol: dict[str, float] | None = None,
    starting_cash: float = 0.0,
    order_request_budget_per_minute: float = 120.0,
    position_tolerance: float = 1e-6,
    cash_tolerance: float = 0.01,
) -> RecoveryState:
    portfolio_state = rebuild_portfolio_truth(
        ledger=ledger,
        balances=balances,
        market_quotes=market_quotes,
        greek_snapshots=greek_snapshots,
        max_loss_by_symbol=max_loss_by_symbol,
        starting_cash=starting_cash,
        broker_confirmed_only=True,
    )

    snapshot = reconcile_order_lifecycle(
        order_events=list(open_orders or []),
        account_activity_events=list(account_activity_events or []),
        order_request_budget_per_minute=order_request_budget_per_minute,
    )

    broker_positions = _position_map(positions)
    local_positions = {row.symbol: row.quantity for row in portfolio_state.positions}
    mismatches: list[str] = []
    for symbol in sorted(set(broker_positions) | set(local_positions)):
        broker_qty = broker_positions.get(symbol, 0.0)
        local_qty = local_positions.get(symbol, 0.0)
        if abs(broker_qty - local_qty) > float(position_tolerance):
            mismatches.append(symbol)

    orphaned_broker_orders, stale_local_orders = detect_orphaned_orders(
        broker_open_orders=open_orders,
        local_open_orders=local_open_orders,
    )

    broker_cash = _extract_broker_cash_balance(balances)
    cash_delta = 0.0
    if broker_cash is not None:
        cash_delta = round(abs(float(broker_cash) - float(portfolio_state.cash_balance)), 6)

    reasons: list[str] = []
    if snapshot.delayed_quotes_detected:
        reasons.append("broker_delayed_quotes_detected")
    if snapshot.request_budget_breached:
        reasons.append("request_budget_breached")
    if snapshot.duplicate_client_order_ids:
        reasons.append("duplicate_client_order_ids")
    if snapshot.duplicate_order_signatures:
        reasons.append("duplicate_order_signatures")
    if mismatches:
        reasons.append("position_mismatch")
    if orphaned_broker_orders:
        reasons.append("orphaned_broker_orders")
    if stale_local_orders:
        reasons.append("stale_local_orders")
    if broker_cash is not None and cash_delta > float(cash_tolerance):
        reasons.append("cash_balance_mismatch")

    return RecoveryState(
        portfolio_state=portfolio_state,
        broker_truth_snapshot=snapshot,
        broker_position_mismatches=tuple(mismatches),
        orphaned_broker_orders=orphaned_broker_orders,
        stale_local_orders=stale_local_orders,
        broker_cash_balance=broker_cash,
        cash_balance_difference=cash_delta,
        parity_ok=(len(reasons) == 0),
        reasons=tuple(reasons),
    )


def require_broker_parity_before_entries(
    recovery_state: RecoveryState,
    *,
    allow_stale_local_only: bool = False,
) -> tuple[bool, tuple[str, ...]]:
    if recovery_state.parity_ok:
        return True, ()
    reasons = set(recovery_state.reasons)
    if allow_stale_local_only and reasons and reasons.issubset({"stale_local_orders"}):
        return True, tuple(sorted(reasons))
    return False, tuple(sorted(reasons))
