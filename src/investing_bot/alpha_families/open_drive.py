from __future__ import annotations

from typing import Any

from ..alpha_registry import AlphaFamilySpec, AlphaSignal


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


def generate_open_drive_signals(feature_rows: list[dict[str, Any]]) -> list[AlphaSignal]:
    signals: list[AlphaSignal] = []
    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not symbol:
            continue

        minutes_from_open = _as_float(row.get("minutes_from_open"), 999.0)
        drive_score = _as_float(row.get("opening_drive_score"), 0.0)
        spread = _as_float(row.get("spread_cost"), 0.01)
        depth = _as_float(row.get("book_depth_contracts"), 0.0)
        confidence = max(0.0, min(1.0, _as_float(row.get("model_confidence"), 0.60)))

        if minutes_from_open < 0 or minutes_from_open > 30:
            continue
        if drive_score < 0.35:
            continue
        if depth < 25:
            continue

        expected_edge = max(0.0, drive_score * 0.03 - spread * 0.5)
        if expected_edge <= 0:
            continue

        side = "buy" if _as_float(row.get("drive_direction"), 1.0) >= 0 else "sell"
        score = expected_edge * confidence * min(1.0, depth / 100.0)
        event_key = str(row.get("event_key") or f"open_drive:{symbol}").strip()
        liquidity_tier = str(row.get("liquidity_tier") or "").strip().lower()
        is_top_tier = liquidity_tier in {"top_tier", "tier1", "top"} or (depth >= 150 and spread <= 0.02)
        evidence_universe = "open_drive_top_tier" if is_top_tier else "open_drive_broad"

        signals.append(
            AlphaSignal(
                family="open_drive",
                symbol=symbol,
                underlying=str(row.get("underlying") or symbol).strip().upper(),
                event_key=event_key,
                side=side,
                expected_edge=round(expected_edge, 8),
                confidence=round(confidence, 6),
                score=round(score, 10),
                metadata={
                    "expected_holding_minutes": _as_float(row.get("expected_holding_minutes"), 30.0),
                    "risk_class": "defined_risk_long_convexity",
                    "opening_drive_score": drive_score,
                    "minutes_from_open": minutes_from_open,
                    "liquidity_tier": liquidity_tier or "unknown",
                    "evidence_universe": evidence_universe,
                },
            )
        )

    return sorted(signals, key=lambda row: (row.score, row.expected_edge), reverse=True)


def open_drive_family() -> tuple[AlphaFamilySpec, callable]:
    spec = AlphaFamilySpec(
        name="open_drive",
        description="Opening-drive liquid options execution",
        risk_class="defined_risk_long_convexity",
        allowed_structures=("long_single", "debit_spread"),
        required_features=("minutes_from_open", "opening_drive_score", "book_depth_contracts", "spread_cost"),
        expected_holding_minutes=30.0,
        default_stage="probe",
    )
    return spec, generate_open_drive_signals
