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


def generate_filing_vol_signals(feature_rows: list[dict[str, Any]]) -> list[AlphaSignal]:
    signals: list[AlphaSignal] = []
    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not symbol:
            continue

        filing_shock = _as_float(row.get("filing_shock_score"), 0.0)
        sec_recent = bool(row.get("sec_recent_filing") or row.get("recent_8k") or filing_shock > 0)
        iv_spread = _as_float(row.get("iv_minus_realized"), 0.0)
        confidence = max(0.0, min(1.0, _as_float(row.get("model_confidence"), 0.60)))
        liquidity_score = max(0.0, min(1.0, _as_float(row.get("liquidity_score"), 0.60)))

        if not sec_recent:
            continue
        if filing_shock < 0.20:
            continue

        expected_edge = max(0.0, (filing_shock * 0.04) + (iv_spread * 0.30) - 0.002)
        if expected_edge <= 0:
            continue

        score = max(0.0, expected_edge * confidence * liquidity_score)
        event_key = str(row.get("event_key") or row.get("filing_id") or f"filing:{symbol}").strip()
        side = "sell" if iv_spread > 0 else "buy"

        signals.append(
            AlphaSignal(
                family="filing_vol",
                symbol=symbol,
                underlying=str(row.get("underlying") or symbol).strip().upper(),
                event_key=event_key,
                side=side,
                expected_edge=round(expected_edge, 8),
                confidence=round(confidence, 6),
                score=round(score, 10),
                metadata={
                    "expected_holding_minutes": _as_float(row.get("expected_holding_minutes"), 240.0),
                    "risk_class": "defined_risk_long_convexity",
                    "filing_shock_score": filing_shock,
                    "iv_minus_realized": iv_spread,
                },
            )
        )

    return sorted(signals, key=lambda row: (row.score, row.expected_edge), reverse=True)


def filing_vol_family() -> tuple[AlphaFamilySpec, callable]:
    spec = AlphaFamilySpec(
        name="filing_vol",
        description="SEC filing shock volatility repricing",
        risk_class="defined_risk_long_convexity",
        allowed_structures=("long_single", "debit_spread", "calendar"),
        required_features=("sec_recent_filing", "filing_shock_score", "iv_minus_realized", "liquidity_score"),
        expected_holding_minutes=240.0,
        default_stage="probe",
    )
    return spec, generate_filing_vol_signals
