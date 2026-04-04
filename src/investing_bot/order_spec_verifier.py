from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"buy", "buy_to_open", "buy_to_close"}:
        return "buy"
    if text in {"sell", "sell_to_open", "sell_to_close"}:
        return "sell"
    return text


def _normalize_order_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    aliases = {
        "lmt": "limit",
        "mkt": "market",
        "stop_lmt": "stop_limit",
        "stp lmt": "stop_limit",
    }
    return aliases.get(text, text)


def _normalize_legs(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    rows: list[dict[str, Any]] = []
    for leg in value:
        if not isinstance(leg, dict):
            continue
        rows.append(
            {
                "symbol": str(leg.get("symbol") or leg.get("instrument") or "").strip().upper(),
                "side": _normalize_side(leg.get("side") or leg.get("instruction")),
                "ratio": int(_as_float(leg.get("ratio"), default=1.0)),
                "quantity": _as_float(leg.get("quantity"), default=0.0),
            }
        )
    return tuple(rows)


def normalize_order_spec(spec: dict[str, Any] | None) -> dict[str, Any]:
    row = spec if isinstance(spec, dict) else {}
    return {
        "symbol": str(row.get("symbol") or row.get("ticker") or "").strip().upper(),
        "side": _normalize_side(row.get("side") or row.get("instruction")),
        "order_type": _normalize_order_type(row.get("order_type") or row.get("type")),
        "quantity": _as_float(row.get("quantity") or row.get("order_quantity"), default=0.0),
        "limit_price": _as_float(row.get("limit_price") or row.get("price"), default=0.0),
        "stop_price": _as_float(row.get("stop_price") or row.get("stop"), default=0.0),
        "time_in_force": str(row.get("time_in_force") or row.get("tif") or "").strip().upper(),
        "legs": _normalize_legs(row.get("legs")),
        "native_walk_limit": bool(row.get("native_walk_limit") or row.get("walk_limit") or False),
    }


@dataclass(frozen=True)
class OrderSpecDiff:
    field: str
    intended: Any
    actual: Any
    severity: str


@dataclass(frozen=True)
class OrderSpecVerification:
    matches: bool
    executable: bool
    diffs: tuple[OrderSpecDiff, ...]
    intended: dict[str, Any]
    actual: dict[str, Any]


def _severity(field: str) -> str:
    if field in {"symbol", "side", "order_type"}:
        return "high"
    if field in {"quantity", "limit_price", "time_in_force", "legs"}:
        return "medium"
    return "low"


def _float_equal(a: Any, b: Any, tolerance: float) -> bool:
    return abs(_as_float(a, 0.0) - _as_float(b, 0.0)) <= abs(float(tolerance))


def verify_order_spec(
    *,
    intended: dict[str, Any],
    actual: dict[str, Any],
    price_tolerance: float = 1e-6,
    quantity_tolerance: float = 1e-6,
    allowed_mismatches: tuple[str, ...] | list[str] | None = None,
) -> OrderSpecVerification:
    allowed = {str(field).strip() for field in (allowed_mismatches or []) if str(field).strip()}
    left = normalize_order_spec(intended)
    right = normalize_order_spec(actual)

    diffs: list[OrderSpecDiff] = []
    for field in ("symbol", "side", "order_type", "quantity", "limit_price", "stop_price", "time_in_force", "legs", "native_walk_limit"):
        if field in allowed:
            continue
        lval = left.get(field)
        rval = right.get(field)

        same = False
        if field == "quantity":
            same = _float_equal(lval, rval, quantity_tolerance)
        elif field in {"limit_price", "stop_price"}:
            same = _float_equal(lval, rval, price_tolerance)
        else:
            same = lval == rval

        if not same:
            diffs.append(
                OrderSpecDiff(
                    field=field,
                    intended=lval,
                    actual=rval,
                    severity=_severity(field),
                )
            )

    blocking = any(diff.severity == "high" for diff in diffs)
    return OrderSpecVerification(
        matches=len(diffs) == 0,
        executable=not blocking,
        diffs=tuple(diffs),
        intended=left,
        actual=right,
    )


def walk_limit_api_verified(capabilities: dict[str, Any] | None = None) -> bool:
    row = capabilities if isinstance(capabilities, dict) else {}
    return bool(row.get("native_walk_limit_api_verified") or row.get("walk_limit_api_verified"))
