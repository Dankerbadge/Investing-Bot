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


def generate_post_event_iv_signals(feature_rows: list[dict[str, Any]]) -> list[AlphaSignal]:
    signals: list[AlphaSignal] = []
    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
        if not symbol:
            continue

        hours_since_event = _as_float(row.get("hours_since_event"), 999.0)
        iv_ratio = _as_float(row.get("post_event_iv_ratio"), 1.0)
        mean_reversion_score = _as_float(row.get("mean_reversion_score"), 0.0)
        confidence = max(0.0, min(1.0, _as_float(row.get("model_confidence"), 0.55)))
        liquidity_score = max(0.0, min(1.0, _as_float(row.get("liquidity_score"), 0.60)))

        if hours_since_event > 24.0:
            continue
        if iv_ratio < 1.05:
            continue

        expected_edge = max(0.0, (iv_ratio - 1.0) * 0.05 + mean_reversion_score * 0.02 - 0.002)
        if expected_edge <= 0:
            continue

        score = expected_edge * confidence * liquidity_score
        event_key = str(row.get("event_key") or row.get("earnings_id") or f"post_event:{symbol}").strip()
        side = "sell"

        signals.append(
            AlphaSignal(
                family="post_event_iv",
                symbol=symbol,
                underlying=str(row.get("underlying") or symbol).strip().upper(),
                event_key=event_key,
                side=side,
                expected_edge=round(expected_edge, 8),
                confidence=round(confidence, 6),
                score=round(score, 10),
                metadata={
                    "expected_holding_minutes": _as_float(row.get("expected_holding_minutes"), 360.0),
                    "risk_class": "credit_spread_defined_risk",
                    "post_event_iv_ratio": iv_ratio,
                    "mean_reversion_score": mean_reversion_score,
                    "hours_since_event": hours_since_event,
                },
            )
        )

    return sorted(signals, key=lambda row: (row.score, row.expected_edge), reverse=True)


def post_event_iv_family() -> tuple[AlphaFamilySpec, callable]:
    spec = AlphaFamilySpec(
        name="post_event_iv",
        description="Post-event implied volatility compression mean reversion",
        risk_class="credit_spread_defined_risk",
        allowed_structures=("credit_spread", "iron_condor", "calendar"),
        required_features=("hours_since_event", "post_event_iv_ratio", "mean_reversion_score", "liquidity_score"),
        expected_holding_minutes=360.0,
        default_stage="probe",
    )
    return spec, generate_post_event_iv_signals
