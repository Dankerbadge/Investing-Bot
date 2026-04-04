from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _copy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(row) if isinstance(row, dict) else {} for row in rows]


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def inject_stream_gap(
    rows: list[dict[str, Any]],
    *,
    gap_seconds: float,
    at_index: int = 0,
    time_key: str = "timestamp",
) -> list[dict[str, Any]]:
    copied = _copy_rows(rows)
    if not copied:
        return copied
    idx = max(0, min(len(copied) - 1, int(at_index)))

    base_time = _parse_time(copied[idx].get(time_key))
    if base_time is None:
        base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        copied[idx][time_key] = _format_time(base_time)

    shift = timedelta(seconds=max(0.0, float(gap_seconds)))
    for pos in range(idx + 1, len(copied)):
        raw = copied[pos].get(time_key)
        parsed = _parse_time(raw)
        if parsed is None:
            parsed = base_time + timedelta(seconds=pos)
        copied[pos][time_key] = _format_time(parsed + shift)
        copied[pos]["stream_gap_seconds"] = max(
            float(copied[pos].get("stream_gap_seconds") or 0.0),
            float(gap_seconds),
        )
    return copied


def inject_delayed_quotes(
    rows: list[dict[str, Any]],
    *,
    start_index: int = 0,
    every_n: int = 1,
) -> list[dict[str, Any]]:
    copied = _copy_rows(rows)
    if every_n <= 0:
        every_n = 1
    for idx in range(max(0, int(start_index)), len(copied)):
        if ((idx - max(0, int(start_index))) % every_n) == 0:
            copied[idx]["quote_mode"] = "delayed"
            copied[idx]["delayed_quotes_detected"] = True
    return copied


def inject_order_change_race(
    order_rows: list[dict[str, Any]],
    *,
    order_id: str,
    time_key: str = "timestamp",
) -> list[dict[str, Any]]:
    copied = _copy_rows(order_rows)
    oid = str(order_id or "").strip()
    if not oid:
        return copied

    base_time = datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)
    copied.append(
        {
            "order_id": oid,
            "status": "cancelled",
            time_key: _format_time(base_time),
            "event_type": "cancel_ack",
        }
    )
    copied.append(
        {
            "order_id": oid,
            "status": "filled",
            time_key: _format_time(base_time),
            "fill_quantity": 1,
            "fill_price": 1.0,
            "event_type": "fill",
        }
    )
    return copied


def inject_request_burst(
    order_rows: list[dict[str, Any]],
    *,
    burst_count: int,
    timestamp: str | None = None,
) -> list[dict[str, Any]]:
    copied = _copy_rows(order_rows)
    ts = str(timestamp or "").strip() or _format_time(datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc))
    count = max(0, int(burst_count))
    for idx in range(count):
        copied.append(
            {
                "order_id": f"burst-{idx}",
                "status": "submitted",
                "timestamp": ts,
                "request_id": f"req-{idx}",
            }
        )
    return copied
