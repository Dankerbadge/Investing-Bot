from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FRED_SERIES_ENDPOINT = "https://api.stlouisfed.org/fred/series/observations"
CBOE_HISTORICAL_OPTIONS_STATS = "https://ww2.cboe.com/us/options/market_statistics/historical_data/"


@dataclass(frozen=True)
class RegimeContext:
    vix_regime: str
    put_call_regime: str
    macro_regime: str
    liquidity_regime: str
    risk_multiplier: float


def infer_regime_context(metadata: dict[str, Any] | None) -> RegimeContext:
    data = metadata or {}
    vix = float(data.get("vix_level") or data.get("vix") or 18.0)
    put_call = float(data.get("put_call_ratio") or 0.8)
    macro_state = str(data.get("macro_regime") or "").strip().lower()
    spread_cost = float(data.get("spread_cost") or 0.02)

    if vix >= 35:
        vix_regime = "extreme"
        vix_mult = 0.50
    elif vix >= 25:
        vix_regime = "high"
        vix_mult = 0.70
    elif vix >= 15:
        vix_regime = "normal"
        vix_mult = 1.0
    else:
        vix_regime = "low"
        vix_mult = 0.90

    if put_call >= 1.3:
        put_call_regime = "crowded_puts"
        pcr_mult = 0.85
    elif put_call <= 0.6:
        put_call_regime = "crowded_calls"
        pcr_mult = 0.90
    else:
        put_call_regime = "balanced"
        pcr_mult = 1.0

    if macro_state in {"release", "event", "hot"}:
        macro_regime = "macro_event"
        macro_mult = 0.80
    elif macro_state in {"risk_off", "tightening"}:
        macro_regime = "risk_off"
        macro_mult = 0.85
    else:
        macro_regime = "stable"
        macro_mult = 1.0

    if spread_cost > 0.05:
        liquidity_regime = "illiquid"
        liq_mult = 0.65
    elif spread_cost > 0.03:
        liquidity_regime = "thin"
        liq_mult = 0.80
    else:
        liquidity_regime = "liquid"
        liq_mult = 1.0

    risk_multiplier = max(0.0, min(1.0, vix_mult * pcr_mult * macro_mult * liq_mult))
    return RegimeContext(
        vix_regime=vix_regime,
        put_call_regime=put_call_regime,
        macro_regime=macro_regime,
        liquidity_regime=liquidity_regime,
        risk_multiplier=round(risk_multiplier, 6),
    )


def regime_penalty(regime: RegimeContext) -> float:
    return round((1.0 - regime.risk_multiplier) * 0.02, 6)


def regime_reasons(regime: RegimeContext) -> list[str]:
    reasons: list[str] = []
    if regime.vix_regime in {"high", "extreme"}:
        reasons.append("regime_high_volatility")
    if regime.put_call_regime != "balanced":
        reasons.append("regime_crowded_positioning")
    if regime.macro_regime != "stable":
        reasons.append("regime_macro_event")
    if regime.liquidity_regime != "liquid":
        reasons.append("regime_liquidity_thin")
    return reasons
