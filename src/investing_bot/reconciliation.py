from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OrderLifecycle:
    order_id: str
    client_order_id: str
    order_signature: str
    first_timestamp: str
    last_timestamp: str
    status_path: tuple[str, ...]
    final_status: str
    requested_quantity: float
    filled_quantity: float
    cancel_replace_count: int
    rejected: bool


@dataclass(frozen=True)
class BrokerTruthSnapshot:
    orders: dict[str, OrderLifecycle]
    delayed_quotes_detected: bool
    duplicate_client_order_ids: tuple[str, ...]
    duplicate_order_signatures: tuple[str, ...]
    observed_requests_per_minute: float
    request_budget_per_minute: float
    request_budget_utilization: float
    request_budget_breached: bool


@dataclass(frozen=True)
class OrderStatusTruth:
    order_id: str
    canonical_status: str
    broker_confirmed: bool
    local_status: str
    pending_reconciliation: bool


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


def _timestamp_of(row: dict[str, Any]) -> str:
    for key in (
        "timestamp",
        "updated_at",
        "event_time",
        "created_at",
        "time",
    ):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _status_of(row: dict[str, Any]) -> str:
    for key in ("status", "order_status", "event_type", "activity_type"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            return value
    return "unknown"


def _order_id_of(row: dict[str, Any]) -> str:
    for key in ("order_id", "id", "client_order_id", "orderId"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _client_order_id_of(row: dict[str, Any]) -> str:
    for key in ("client_order_id", "clientOrderId", "correlation_id", "request_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _order_signature_of(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "").strip().upper()
    side = str(row.get("side") or row.get("instruction") or "").strip().lower()
    limit_price = _as_float(row.get("limit_price") or row.get("price"), default=0.0)
    quantity = _as_float(row.get("requested_quantity") or row.get("order_quantity") or row.get("quantity"), default=0.0)
    if not ticker:
        return ""
    return f"{ticker}|{side}|{round(limit_price, 6)}|{round(quantity, 4)}"


def _is_delayed_quote_record(row: dict[str, Any]) -> bool:
    text_fields = [
        str(row.get("quote_mode") or "").strip().lower(),
        str(row.get("data_quality") or "").strip().lower(),
        str(row.get("entitlement") or "").strip().lower(),
        str(row.get("note") or "").strip().lower(),
    ]
    return any("delayed" in field for field in text_fields if field)


def _sort_key(timestamp_text: str) -> tuple[int, str]:
    if not timestamp_text:
        return (1, "")
    try:
        parsed = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        return (0, parsed.isoformat())
    except ValueError:
        return (1, timestamp_text)


def _timestamp_to_epoch(timestamp_text: str) -> float | None:
    if not timestamp_text:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
        return parsed.timestamp()
    except ValueError:
        return None


def _max_requests_per_minute(events: list[dict[str, Any]]) -> float:
    epochs: list[float] = []
    for row in events:
        epoch = _timestamp_to_epoch(_timestamp_of(row))
        if epoch is not None:
            epochs.append(epoch)
    if not epochs:
        return 0.0
    epochs.sort()
    left = 0
    best = 0
    for right, value in enumerate(epochs):
        while left <= right and (value - epochs[left]) > 60.0:
            left += 1
        window = right - left + 1
        if window > best:
            best = window
    return float(best)


def _is_terminal_status(status: str) -> bool:
    return status in {"filled", "complete", "cancelled", "canceled", "rejected", "expired"}


def reconcile_order_lifecycle(
    order_events: list[dict[str, Any]],
    account_activity_events: list[dict[str, Any]] | None = None,
    order_request_budget_per_minute: float = 120.0,
) -> BrokerTruthSnapshot:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order_id_to_client: dict[str, str] = {}
    order_id_to_signature: dict[str, str] = {}
    client_to_order_ids: dict[str, set[str]] = {}
    signature_to_order_ids: dict[str, set[str]] = {}

    for row in order_events:
        if not isinstance(row, dict):
            continue
        order_id = _order_id_of(row)
        if not order_id:
            continue
        grouped.setdefault(order_id, []).append(row)
        client_id = _client_order_id_of(row)
        if client_id:
            order_id_to_client.setdefault(order_id, client_id)
            client_to_order_ids.setdefault(client_id, set()).add(order_id)
        signature = _order_signature_of(row)
        if signature:
            order_id_to_signature.setdefault(order_id, signature)
            signature_to_order_ids.setdefault(signature, set()).add(order_id)

    if account_activity_events:
        for row in account_activity_events:
            if not isinstance(row, dict):
                continue
            order_id = _order_id_of(row)
            if not order_id:
                continue
            grouped.setdefault(order_id, []).append(row)
            client_id = _client_order_id_of(row)
            if client_id:
                order_id_to_client.setdefault(order_id, client_id)
                client_to_order_ids.setdefault(client_id, set()).add(order_id)
            signature = _order_signature_of(row)
            if signature:
                order_id_to_signature.setdefault(order_id, signature)
                signature_to_order_ids.setdefault(signature, set()).add(order_id)

    lifecycles: dict[str, OrderLifecycle] = {}

    for order_id, rows in grouped.items():
        rows_sorted = sorted(rows, key=lambda row: _sort_key(_timestamp_of(row)))
        timestamps = [_timestamp_of(row) for row in rows_sorted if _timestamp_of(row)]
        statuses = tuple(_status_of(row) for row in rows_sorted)
        requested_qty = max(
            _as_float(row.get("requested_quantity") or row.get("order_quantity") or row.get("quantity"), default=0.0)
            for row in rows_sorted
        )
        filled_qty = sum(
            _as_float(row.get("fill_quantity") or row.get("filled_quantity"), default=0.0)
            for row in rows_sorted
        )
        cancel_replace_count = sum(
            1
            for status in statuses
            if status in {"replaced", "replace", "cancel_replaced", "changed", "modify"}
        )
        final_status = statuses[-1] if statuses else "unknown"
        rejected = any(status in {"rejected", "cancel_rejected"} for status in statuses)

        lifecycles[order_id] = OrderLifecycle(
            order_id=order_id,
            client_order_id=order_id_to_client.get(order_id, ""),
            order_signature=order_id_to_signature.get(order_id, ""),
            first_timestamp=timestamps[0] if timestamps else "",
            last_timestamp=timestamps[-1] if timestamps else "",
            status_path=statuses,
            final_status=final_status,
            requested_quantity=requested_qty,
            filled_quantity=filled_qty,
            cancel_replace_count=cancel_replace_count,
            rejected=rejected,
        )

    duplicate_client_order_ids = tuple(
        sorted(client_id for client_id, order_ids in client_to_order_ids.items() if len(order_ids) > 1)
    )
    duplicate_order_signatures = tuple(
        sorted(signature for signature, order_ids in signature_to_order_ids.items() if len(order_ids) > 1)
    )

    observed_requests_per_minute = _max_requests_per_minute(order_events)
    budget = max(0.0, float(order_request_budget_per_minute))
    utilization = (observed_requests_per_minute / budget) if budget > 0 else 0.0
    request_budget_breached = bool(budget > 0 and observed_requests_per_minute > budget)

    delayed_quotes_detected = any(_is_delayed_quote_record(row) for row in (account_activity_events or []))

    return BrokerTruthSnapshot(
        orders=lifecycles,
        delayed_quotes_detected=delayed_quotes_detected,
        duplicate_client_order_ids=duplicate_client_order_ids,
        duplicate_order_signatures=duplicate_order_signatures,
        observed_requests_per_minute=round(observed_requests_per_minute, 6),
        request_budget_per_minute=round(budget, 6),
        request_budget_utilization=round(utilization, 6),
        request_budget_breached=request_budget_breached,
    )


def resolve_order_status(
    *,
    order_id: str,
    local_status: str,
    snapshot: BrokerTruthSnapshot | None,
) -> OrderStatusTruth:
    normalized_local = str(local_status or "").strip().lower() or "unknown"
    if snapshot is None:
        return OrderStatusTruth(
            order_id=order_id,
            canonical_status=normalized_local,
            broker_confirmed=False,
            local_status=normalized_local,
            pending_reconciliation=True,
        )
    lifecycle = snapshot.orders.get(str(order_id or "").strip())
    if lifecycle is None:
        return OrderStatusTruth(
            order_id=order_id,
            canonical_status=normalized_local,
            broker_confirmed=False,
            local_status=normalized_local,
            pending_reconciliation=True,
        )
    status = lifecycle.final_status or "unknown"
    return OrderStatusTruth(
        order_id=order_id,
        canonical_status=status,
        broker_confirmed=True,
        local_status=normalized_local,
        pending_reconciliation=not _is_terminal_status(status),
    )
