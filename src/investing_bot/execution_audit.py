from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .order_spec_verifier import OrderSpecVerification, verify_order_spec


@dataclass(frozen=True)
class ExecutionAudit:
    order_id: str
    spec_matches: bool
    executable_spec: bool
    final_status: str
    requested_quantity: float
    filled_quantity: float
    average_fill_price: float
    cancel_replace_count: int
    partial_fill_count: int
    race_detected: bool
    adverse_slippage_vs_limit: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionAuditSummary:
    order_count: int
    mismatch_count: int
    race_count: int
    mean_adverse_slippage: float
    fill_rate: float


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


def _status_of(row: dict[str, Any]) -> str:
    for key in ("status", "order_status", "event_type", "activity_type"):
        text = str(row.get(key) or "").strip().lower()
        if text:
            return text
    return "unknown"


def audit_execution_path(
    *,
    order_id: str,
    intended_spec: dict[str, Any],
    broker_spec: dict[str, Any],
    lifecycle_rows: list[dict[str, Any]],
    price_tolerance: float = 1e-6,
    quantity_tolerance: float = 1e-6,
) -> ExecutionAudit:
    verification: OrderSpecVerification = verify_order_spec(
        intended=intended_spec,
        actual=broker_spec,
        price_tolerance=price_tolerance,
        quantity_tolerance=quantity_tolerance,
    )

    statuses = [_status_of(row) for row in lifecycle_rows if isinstance(row, dict)]
    final_status = statuses[-1] if statuses else "unknown"

    requested_quantity = _as_float(
        broker_spec.get("quantity")
        or broker_spec.get("order_quantity")
        or intended_spec.get("quantity")
        or intended_spec.get("order_quantity"),
        default=0.0,
    )

    fill_rows = [row for row in lifecycle_rows if _as_float(row.get("fill_quantity") or row.get("filled_quantity"), 0.0) > 0]
    filled_quantity = sum(_as_float(row.get("fill_quantity") or row.get("filled_quantity"), 0.0) for row in fill_rows)

    notional = 0.0
    for row in fill_rows:
        qty = _as_float(row.get("fill_quantity") or row.get("filled_quantity"), 0.0)
        price = _as_float(row.get("fill_price") or row.get("average_price") or row.get("price"), 0.0)
        notional += qty * price
    average_fill_price = (notional / filled_quantity) if filled_quantity > 0 else 0.0

    cancel_replace_count = sum(
        1
        for status in statuses
        if status in {"replaced", "replace", "cancel_replaced", "changed", "modify"}
    )
    partial_fill_count = sum(1 for status in statuses if status in {"partial_fill", "partially_filled"})
    race_detected = ("cancelled" in statuses or "canceled" in statuses) and filled_quantity > 0

    side = str(intended_spec.get("side") or intended_spec.get("instruction") or "").strip().lower()
    limit_price = _as_float(intended_spec.get("limit_price") or intended_spec.get("price"), 0.0)
    adverse_slippage = 0.0
    if limit_price > 0 and average_fill_price > 0:
        if side.startswith("buy"):
            adverse_slippage = max(0.0, average_fill_price - limit_price)
        elif side.startswith("sell"):
            adverse_slippage = max(0.0, limit_price - average_fill_price)

    reasons: list[str] = []
    if not verification.matches:
        reasons.append("order_spec_mismatch")
    if not verification.executable:
        reasons.append("non_executable_spec_mismatch")
    if race_detected:
        reasons.append("cancel_fill_race_detected")
    if final_status in {"rejected", "cancel_rejected"}:
        reasons.append("order_rejected")
    if requested_quantity > 0 and filled_quantity < requested_quantity and final_status in {"filled", "complete"}:
        reasons.append("filled_quantity_below_request")

    return ExecutionAudit(
        order_id=str(order_id or "").strip(),
        spec_matches=verification.matches,
        executable_spec=verification.executable,
        final_status=final_status,
        requested_quantity=round(requested_quantity, 6),
        filled_quantity=round(filled_quantity, 6),
        average_fill_price=round(average_fill_price, 6),
        cancel_replace_count=cancel_replace_count,
        partial_fill_count=partial_fill_count,
        race_detected=race_detected,
        adverse_slippage_vs_limit=round(adverse_slippage, 6),
        reasons=tuple(sorted(set(reasons))),
    )


def summarize_execution_audits(audits: list[ExecutionAudit] | tuple[ExecutionAudit, ...]) -> ExecutionAuditSummary:
    rows = list(audits)
    if not rows:
        return ExecutionAuditSummary(
            order_count=0,
            mismatch_count=0,
            race_count=0,
            mean_adverse_slippage=0.0,
            fill_rate=0.0,
        )

    mismatch = sum(1 for row in rows if not row.spec_matches)
    races = sum(1 for row in rows if row.race_detected)
    slippage = sum(max(0.0, row.adverse_slippage_vs_limit) for row in rows) / len(rows)
    fills = sum(1 for row in rows if row.filled_quantity > 0)

    return ExecutionAuditSummary(
        order_count=len(rows),
        mismatch_count=mismatch,
        race_count=races,
        mean_adverse_slippage=round(slippage, 6),
        fill_rate=round(fills / len(rows), 6),
    )
