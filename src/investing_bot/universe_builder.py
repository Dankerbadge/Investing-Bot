from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .alpha_registry import AlphaRegistry
from .instrument_registry import InstrumentRegistry


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


def _as_int(value: Any, default: int = 0) -> int:
    return int(round(_as_float(value, float(default))))


def _symbol_of(row: dict[str, Any]) -> str:
    return str(row.get("symbol") or row.get("ticker") or "").strip().upper()


def _underlying_of(row: dict[str, Any], symbol: str) -> str:
    return str(row.get("underlying") or symbol).strip().upper()


def _feature_present(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


@dataclass(frozen=True)
class UniverseConstraints:
    min_liquidity_score: float = 0.45
    min_book_depth_contracts: int = 25
    max_spread_cost: float = 0.08
    max_quote_age_seconds: float = 5.0
    require_realtime_quotes: bool = False
    allow_adjusted_options: bool = False
    allow_non_standard_expirations: bool = False
    allow_undefined_risk: bool = False
    min_market_cap_usd: float = 0.0


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    underlying: str
    quality_score: float
    eligible: bool
    reasons: tuple[str, ...]
    feature_row: dict[str, Any]


def evaluate_universe_member(
    row: dict[str, Any],
    *,
    constraints: UniverseConstraints | None = None,
    instrument_registry: InstrumentRegistry | None = None,
) -> UniverseMember | None:
    if not isinstance(row, dict):
        return None

    cfg = constraints or UniverseConstraints()
    symbol = _symbol_of(row)
    if not symbol:
        return None
    underlying = _underlying_of(row, symbol)

    liquidity_score = max(0.0, min(1.0, _as_float(row.get("liquidity_score"), 0.0)))
    depth = max(0, _as_int(row.get("book_depth_contracts"), 0))
    spread = max(0.0, _as_float(row.get("spread_cost"), 0.0))
    quote_age = max(0.0, _as_float(row.get("quote_age_seconds"), 0.0))
    market_cap = max(0.0, _as_float(row.get("market_cap_usd"), 0.0))
    quote_tier = str(row.get("quote_quality_tier") or "").strip().lower()

    reasons: list[str] = []
    if liquidity_score < float(cfg.min_liquidity_score):
        reasons.append("liquidity_score_too_low")
    if depth < int(cfg.min_book_depth_contracts):
        reasons.append("book_depth_too_low")
    if spread > float(cfg.max_spread_cost):
        reasons.append("spread_cost_too_high")
    if quote_age > float(cfg.max_quote_age_seconds):
        reasons.append("quote_age_too_high")
    if market_cap < float(cfg.min_market_cap_usd):
        reasons.append("market_cap_too_low")
    if cfg.require_realtime_quotes and quote_tier in {"delayed", "stale"}:
        reasons.append("quote_quality_not_realtime")

    if instrument_registry is not None:
        allowed, instrument_reasons = instrument_registry.evaluate_trade(
            symbol=symbol,
            allow_adjusted=cfg.allow_adjusted_options,
            allow_non_standard=cfg.allow_non_standard_expirations,
            allow_undefined_risk=cfg.allow_undefined_risk,
        )
        if not allowed:
            reasons.extend(list(instrument_reasons))

    spread_quality = max(0.0, 1.0 - min(1.0, spread / max(0.0001, float(cfg.max_spread_cost))))
    depth_quality = min(1.0, depth / max(1.0, float(cfg.min_book_depth_contracts * 4)))
    quote_quality = max(0.0, 1.0 - min(1.0, quote_age / max(0.0001, float(cfg.max_quote_age_seconds))))
    quality_score = round((0.45 * liquidity_score) + (0.30 * depth_quality) + (0.15 * spread_quality) + (0.10 * quote_quality), 6)

    member_row = dict(row)
    member_row["symbol"] = symbol
    member_row["underlying"] = underlying
    member_row["universe_quality_score"] = quality_score

    return UniverseMember(
        symbol=symbol,
        underlying=underlying,
        quality_score=quality_score,
        eligible=len(reasons) == 0,
        reasons=tuple(sorted(set(reasons))),
        feature_row=member_row,
    )


def build_tradable_universe(
    feature_rows: list[dict[str, Any]],
    *,
    constraints: UniverseConstraints | None = None,
    instrument_registry: InstrumentRegistry | None = None,
    max_symbols: int | None = None,
    eligible_only: bool = True,
) -> tuple[UniverseMember, ...]:
    members: list[UniverseMember] = []
    for row in feature_rows:
        member = evaluate_universe_member(row, constraints=constraints, instrument_registry=instrument_registry)
        if member is None:
            continue
        if eligible_only and not member.eligible:
            continue
        members.append(member)

    members.sort(key=lambda item: (item.quality_score, item.symbol), reverse=True)
    if max_symbols is not None and max_symbols >= 0:
        members = members[: max_symbols or 0]
    return tuple(members)


def rows_for_alpha_family(
    feature_rows: list[dict[str, Any]],
    *,
    family_name: str,
    alpha_registry: AlphaRegistry,
) -> list[dict[str, Any]]:
    spec = alpha_registry.get_spec(family_name)
    if spec is None:
        return []

    required = tuple(spec.required_features)
    rows: list[dict[str, Any]] = []
    for row in feature_rows:
        if not isinstance(row, dict):
            continue
        missing = [key for key in required if not _feature_present(row.get(key))]
        if missing:
            continue
        rows.append(dict(row))
    return rows


def build_alpha_universe(
    feature_rows: list[dict[str, Any]],
    *,
    alpha_registry: AlphaRegistry,
    enabled_families: list[str] | tuple[str, ...] | None = None,
    constraints: UniverseConstraints | None = None,
    instrument_registry: InstrumentRegistry | None = None,
    max_symbols: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    tradable_members = build_tradable_universe(
        feature_rows,
        constraints=constraints,
        instrument_registry=instrument_registry,
        max_symbols=max_symbols,
        eligible_only=True,
    )
    tradable_rows = [member.feature_row for member in tradable_members]

    if enabled_families:
        family_names = tuple(dict.fromkeys(str(name).strip().lower() for name in enabled_families if str(name).strip()))
    else:
        family_names = alpha_registry.available_families()

    result: dict[str, list[dict[str, Any]]] = {}
    for family in family_names:
        result[family] = rows_for_alpha_family(
            tradable_rows,
            family_name=family,
            alpha_registry=alpha_registry,
        )
    return result
