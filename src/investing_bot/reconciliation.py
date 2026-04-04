from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class OrderLifecycle:
    order_id: str
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


def reconcile_order_lifecycle(
    order_events: list[dict[str, Any]],
    account_activity_events: list[dict[str, Any]] | None = None,
) -> BrokerTruthSnapshot:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for row in order_events:
        if not isinstance(row, dict):
            continue
        order_id = _order_id_of(row)
        if not order_id:
            continue
        grouped.setdefault(order_id, []).append(row)

    if account_activity_events:
        for row in account_activity_events:
            if not isinstance(row, dict):
                continue
            order_id = _order_id_of(row)
            if not order_id:
                continue
            grouped.setdefault(order_id, []).append(row)

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
            first_timestamp=timestamps[0] if timestamps else "",
            last_timestamp=timestamps[-1] if timestamps else "",
            status_path=statuses,
            final_status=final_status,
            requested_quantity=requested_qty,
            filled_quantity=filled_qty,
            cancel_replace_count=cancel_replace_count,
            rejected=rejected,
        )

    delayed_quotes_detected = any(_is_delayed_quote_record(row) for row in (account_activity_events or []))

    return BrokerTruthSnapshot(
        orders=lifecycles,
        delayed_quotes_detected=delayed_quotes_detected,
    )
