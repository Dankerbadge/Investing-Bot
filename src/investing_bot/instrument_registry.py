from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True)
class InstrumentProfile:
    symbol: str
    underlying: str
    expiration_type: str = "standard"
    adjusted_option: bool = False
    american_option: bool = True
    defined_risk: bool = True
    liquidity_tier: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InstrumentRegistry:
    profiles: dict[str, InstrumentProfile] = field(default_factory=dict)

    def register(self, profile: InstrumentProfile) -> None:
        symbol = str(profile.symbol or "").strip().upper()
        if not symbol:
            return
        self.profiles[symbol] = profile

    def get(self, symbol: str) -> InstrumentProfile | None:
        key = str(symbol or "").strip().upper()
        if not key:
            return None
        return self.profiles.get(key)

    def evaluate_trade(
        self,
        *,
        symbol: str,
        allow_adjusted: bool = False,
        allow_non_standard: bool = False,
        allow_undefined_risk: bool = False,
    ) -> tuple[bool, tuple[str, ...]]:
        profile = self.get(symbol)
        if profile is None:
            return False, ("instrument_not_registered",)

        reasons: list[str] = []
        expiration_type = str(profile.expiration_type or "").strip().lower()
        if profile.adjusted_option and not allow_adjusted:
            reasons.append("adjusted_option_blocked")
        if expiration_type in {"weekly", "quarterly", "non_standard"} and not allow_non_standard:
            reasons.append("non_standard_expiration_blocked")
        if not profile.defined_risk and not allow_undefined_risk:
            reasons.append("undefined_risk_blocked")

        return (len(reasons) == 0), tuple(reasons)

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> InstrumentRegistry:
        registry = cls()
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            if not symbol:
                continue
            profile = InstrumentProfile(
                symbol=symbol,
                underlying=str(row.get("underlying") or symbol).strip().upper(),
                expiration_type=str(row.get("expiration_type") or "standard").strip().lower() or "standard",
                adjusted_option=_as_bool(row.get("adjusted_option") or row.get("is_adjusted"), default=False),
                american_option=_as_bool(row.get("american_option") or row.get("is_american"), default=True),
                defined_risk=_as_bool(row.get("defined_risk"), default=True),
                liquidity_tier=str(row.get("liquidity_tier") or "unknown").strip().lower() or "unknown",
                metadata={
                    key: value
                    for key, value in row.items()
                    if key not in {"symbol", "ticker", "underlying", "expiration_type", "adjusted_option", "is_adjusted", "american_option", "is_american", "defined_risk", "liquidity_tier"}
                },
            )
            registry.register(profile)
        return registry
